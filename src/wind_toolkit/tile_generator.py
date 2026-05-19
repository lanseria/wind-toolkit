"""XYZ 瓦片生成模块。

从风场数据直接生成透明 RGBA 瓦片（仅风速色斑 + 风向箭头，无底图/标签）。
"""

import json
from datetime import datetime
from pathlib import Path

import matplotlib.colors as mcolors
import numpy as np
import xarray as xr
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

from . import config
from .utils import setup_logger

logger = setup_logger("wind_toolkit.tiles")


def tile_to_wgs84(
    z: int, x: int, y: int, tile_size: int = 256
) -> tuple[np.ndarray, np.ndarray]:
    """将瓦片内每个像素转换为 WGS84 经纬度。"""
    n = 2**z
    px = np.arange(tile_size) + 0.5
    py = np.arange(tile_size) + 0.5

    pixel_x = x * tile_size + px
    pixel_y = y * tile_size + py

    norm_x = pixel_x / (n * tile_size)
    norm_y = pixel_y / (n * tile_size)

    norm_x_grid, norm_y_grid = np.meshgrid(norm_x, norm_y)

    lons = norm_x_grid * 360.0 - 180.0
    lat_rad = np.arctan(np.sinh(np.pi * (1.0 - 2.0 * norm_y_grid)))
    lats = np.degrees(lat_rad)

    return lats, lons


def get_tiles_for_area(
    area: dict[str, float], z: int
) -> list[tuple[int, int, int]]:
    """计算指定缩放级别下覆盖给定区域的所有瓦片坐标。"""
    n = 2**z

    x_min = max(0, int(np.floor((area["west"] + 180) / 360.0 * n)))
    x_max = min(n - 1, int(np.floor((area["east"] + 180) / 360.0 * n)))

    def lat_to_y(lat: float) -> int:
        lat_rad = np.radians(np.clip(lat, -85.051, 85.051))
        y = int(
            np.floor(
                (1.0 - np.log(np.tan(lat_rad) + 1.0 / np.cos(lat_rad)) / np.pi)
                / 2.0
                * n
            )
        )
        return max(0, min(n - 1, y))

    y_min = lat_to_y(area["north"])
    y_max = lat_to_y(area["south"])

    return [(z, tx, ty) for tx in range(x_min, x_max + 1) for ty in range(y_min, y_max + 1)]


def _build_wind_cmap_lut() -> np.ndarray:
    """预计算风速颜色查找表 (256, 4) uint8 RGBA。"""
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "wind_speed",
        list(zip(config.WIND_COLOR_NODES, config.WIND_COLORS)),
    )
    lut = cmap(np.linspace(0, 1, 256))
    return (lut * 255).astype(np.uint8)


def _prepare_wind_data(
    u: np.ndarray,
    v: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    """高斯平滑 + 4x 插值，返回处理后的 speed, u, v 及坐标。"""
    speed = np.sqrt(u**2 + v**2)
    max_speed = float(np.nanmax(speed)) if not np.all(np.isnan(speed)) else 20.0

    interp_factor = 4
    speed_da = xr.DataArray(
        speed, coords={"latitude": lat, "longitude": lon},
        dims=["latitude", "longitude"],
    )
    smoothed = gaussian_filter(speed_da.fillna(0).values, sigma=1.5)
    smoothed_da = xr.DataArray(smoothed, coords=speed_da.coords, dims=speed_da.dims)

    new_lats = np.linspace(lat.min(), lat.max(), len(lat) * interp_factor)
    new_lons = np.linspace(lon.min(), lon.max(), len(lon) * interp_factor)
    vis_speed = smoothed_da.interp(
        latitude=new_lats, longitude=new_lons, method="cubic"
    ).values

    u_da = xr.DataArray(
        u, coords={"latitude": lat, "longitude": lon},
        dims=["latitude", "longitude"],
    )
    v_da = xr.DataArray(
        v, coords={"latitude": lat, "longitude": lon},
        dims=["latitude", "longitude"],
    )
    u_hi = u_da.interp(latitude=new_lats, longitude=new_lons, method="cubic").values
    v_hi = v_da.interp(latitude=new_lats, longitude=new_lons, method="cubic").values

    return vis_speed, u_hi, v_hi, new_lats, new_lons, max_speed


def _build_overlay(
    vis_speed: np.ndarray,
    u_hi: np.ndarray,
    v_hi: np.ndarray,
    vis_lats: np.ndarray,
    vis_lons: np.ndarray,
    max_speed: float,
    cmap_lut: np.ndarray,
    alpha: float = 0.8,
) -> np.ndarray:
    """生成透明 RGBA 叠加层（风速色斑 + 风向箭头）。"""
    # 风速 → colormap
    norm = np.where(np.isnan(vis_speed), 0, np.clip(vis_speed / max_speed, 0, 1))
    indices = np.clip((norm * 255).astype(np.int32), 0, 255)
    overlay = cmap_lut[indices].copy()

    # 半透明，无数据区域全透明
    nan_mask = np.isnan(vis_speed) | (vis_speed < 0.1)
    overlay[..., 3] = np.where(nan_mask, 0, int(alpha * 255)).astype(np.uint8)

    # 绘制风向箭头
    img = Image.fromarray(overlay, "RGBA")
    draw = ImageDraw.Draw(img)

    step_lat = max(1, len(vis_lats) // 30)
    step_lon = max(1, len(vis_lons) // 30)
    for i in range(0, len(vis_lats), step_lat):
        for j in range(0, len(vis_lons), step_lon):
            u_val = u_hi[i, j]
            v_val = v_hi[i, j]
            spd = np.sqrt(u_val**2 + v_val**2)
            if np.isnan(spd) or spd < 0.5:
                continue
            angle = np.arctan2(v_val, u_val)
            length = min(max(3, spd * 1.5), 10)
            dx = length * np.cos(angle)
            dy = -length * np.sin(angle)
            draw.line(
                [(j, i), (j + dx, i + dy)],
                fill=(255, 255, 255, 128),
                width=1,
            )

    return np.array(img)


def _warp_tile(
    src_img: np.ndarray,
    src_bounds: tuple[float, float, float, float],
    z: int,
    x: int,
    y: int,
    tile_size: int = 256,
) -> np.ndarray:
    """将源图（PlateCarree）重投影为 Web Mercator 瓦片。"""
    from scipy.ndimage import map_coordinates

    west, east, south, north = src_bounds
    h, w = src_img.shape[:2]

    lats, lons = tile_to_wgs84(z, x, y, tile_size)

    col = (lons - west) / (east - west) * (w - 1)
    row = (north - lats) / (north - south) * (h - 1)

    tile = np.zeros((tile_size, tile_size, 4), dtype=np.uint8)
    valid = (col >= 0) & (col < w) & (row >= 0) & (row < h)

    for c in range(4):
        ch = map_coordinates(
            src_img[:, :, c].astype(np.float64),
            [row[valid], col[valid]],
            order=1,
            mode="constant",
            cval=0,
        )
        tile[valid, c] = np.clip(ch, 0, 255).astype(np.uint8)

    return tile


def generate_wind_tiles(
    u: np.ndarray,
    v: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    timestamp: str,
    area: dict[str, float] | None = None,
    output_dir: Path | None = None,
    zoom_levels: range | None = None,
    tile_size: int | None = None,
) -> int:
    """从原始风场数据直接生成透明 XYZ 瓦片（仅风速 + 风向，无底图）。

    Args:
        u: 2D U 分量 (lat × lon)
        v: 2D V 分量 (lat × lon)
        lat: 1D 纬度数组
        lon: 1D 经度数组
        timestamp: 时间戳字符串
        area: 地理范围
        output_dir: 瓦片输出目录
        zoom_levels: 缩放级别范围
        tile_size: 瓦片尺寸

    Returns:
        生成的瓦片总数
    """
    if area is None:
        area = config.DISPLAY_AREA
    if output_dir is None:
        output_dir = config.TILE_OUTPUT_DIR
    if zoom_levels is None:
        zoom_levels = range(config.TILE_ZOOM_MIN, config.TILE_ZOOM_MAX + 1)
    if tile_size is None:
        tile_size = config.TILE_SIZE

    logger.info(f"生成透明瓦片: {timestamp}, 缩放 {zoom_levels.start}-{zoom_levels.stop - 1}")

    # 处理数据 + 生成透明叠加层
    vis_speed, u_hi, v_hi, vis_lats, vis_lons, max_speed = _prepare_wind_data(u, v, lat, lon)
    cmap_lut = _build_wind_cmap_lut()
    overlay = _build_overlay(vis_speed, u_hi, v_hi, vis_lats, vis_lons, max_speed, cmap_lut)

    # 切割瓦片
    src_bounds = (vis_lons.min(), vis_lons.max(), vis_lats.min(), vis_lats.max())
    total = 0
    for z in zoom_levels:
        tiles = get_tiles_for_area(area, z)
        for tz, tx, ty in tiles:
            tile_data = _warp_tile(overlay, src_bounds, tz, tx, ty, tile_size)
            out_path = output_dir / str(tz) / str(tx) / str(ty) / f"{timestamp}.png"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(tile_data, "RGBA").save(out_path, "PNG")
        total += len(tiles)
        logger.info(f"  Zoom {z}: {len(tiles)} 个瓦片")

    logger.info(f"瓦片生成完成: 共 {total} 个")
    return total


def update_tiles_manifest(
    datetimes: list[datetime],
    manifest_path: Path | None = None,
) -> None:
    """更新瓦片资源清单文件。

    Args:
        datetimes: datetime 对象列表
        manifest_path: 清单文件路径，为 None 时不更新
    """
    if manifest_path is None:
        return
    now = datetime.now().astimezone().isoformat()

    # 转为 Unix 时间戳（秒）
    new_ts = [int(dt.timestamp()) for dt in datetimes]

    # 读取已有清单
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = {"lastUpdated": now, "timestamps": []}

    # 合并新旧时间戳（去重，排序）
    existing = set(manifest["timestamps"])
    merged = sorted(set(new_ts) | existing)
    manifest["timestamps"] = merged
    manifest["lastUpdated"] = now

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    logger.info(f"瓦片清单已更新: {len(merged)} 个时间戳")
