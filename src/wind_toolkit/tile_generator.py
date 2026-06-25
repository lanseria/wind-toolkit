"""XYZ 瓦片生成模块。

从原始气象数据生成透明 RGBA 瓦片：
- 标量变量（温度/湿度/云量/降水/能见度/气压/HGT/GUST 等）仅含数据色斑
- 风场含风速色斑 + 风向箭头
所有瓦片均无底图、无标签、无地图要素，可直接叠加在任意 Web 地图底图上。
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

logger = setup_logger("atmos_toolkit.tiles")


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


# ── 颜色查找表 ────────────────────────────────────────────────────────
def _build_cmap_lut(cmap_name: str) -> np.ndarray:
    """预计算任意 colormap 的 256-entry RGBA LUT (uint8)。"""
    spec = config.COLORMAPS[cmap_name]
    cmap = mcolors.LinearSegmentedColormap.from_list(
        cmap_name, list(zip(spec["nodes"], spec["colors"]))
    )
    lut = cmap(np.linspace(0, 1, 256))
    return (lut * 255).astype(np.uint8)


def _build_wind_cmap_lut() -> np.ndarray:
    """向后兼容：风速 LUT。"""
    return _build_cmap_lut("wind_speed")


# ── 数据预处理（高斯平滑 + 4x 插值） ─────────────────────────────────
def _interp_data(
    data: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    interp_factor: int = 4,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """仅做 4x 三次插值（不平滑）。Returns: (hi_data, new_lats, new_lons)"""
    da = xr.DataArray(
        data, coords={"latitude": lat, "longitude": lon},
        dims=["latitude", "longitude"],
    )
    new_lats = np.linspace(lat.min(), lat.max(), len(lat) * interp_factor)
    new_lons = np.linspace(lon.min(), lon.max(), len(lon) * interp_factor)
    hi = da.interp(latitude=new_lats, longitude=new_lons, method="cubic")
    return hi.values, new_lats, new_lons


def _smooth_and_interp(
    data: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    sigma: float = 1.5,
    interp_factor: int = 4,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """高斯平滑 + 4x 三次插值。Returns: (hi_data, new_lats, new_lons)"""
    da = xr.DataArray(
        data, coords={"latitude": lat, "longitude": lon},
        dims=["latitude", "longitude"],
    )
    if sigma > 0:
        smoothed = gaussian_filter(da.fillna(0).values, sigma=sigma)
        da = xr.DataArray(smoothed, coords=da.coords, dims=da.dims)
    new_lats = np.linspace(lat.min(), lat.max(), len(lat) * interp_factor)
    new_lons = np.linspace(lon.min(), lon.max(), len(lon) * interp_factor)
    hi = da.interp(latitude=new_lats, longitude=new_lons, method="cubic")
    return hi.values, new_lats, new_lons


def _prepare_wind_data(
    u: np.ndarray,
    v: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    """风场数据预处理。Returns: (vis_speed, u_hi, v_hi, vis_lats, vis_lons, max_speed)"""
    speed = np.sqrt(u**2 + v**2)
    max_speed = float(np.nanmax(speed)) if not np.all(np.isnan(speed)) else 20.0

    vis_speed, vis_lats, vis_lons = _smooth_and_interp(speed, lat, lon, sigma=1.5)
    u_hi, _, _ = _interp_data(u, lat, lon)
    v_hi, _, _ = _interp_data(v, lat, lon)

    return vis_speed, u_hi, v_hi, vis_lats, vis_lons, max_speed


# ── RGBA 叠加层构造 ───────────────────────────────────────────────────
def _build_scalar_overlay(
    vis_data: np.ndarray,
    vmin: float,
    vmax: float,
    cmap_lut: np.ndarray,
    alpha: float = 0.8,
    nan_threshold: float | None = None,
) -> np.ndarray:
    """通用标量场 RGBA 叠加层（无箭头）。"""
    norm = np.where(
        np.isnan(vis_data), 0,
        np.clip((vis_data - vmin) / (vmax - vmin + 1e-9), 0, 1),
    )
    indices = np.clip((norm * 255).astype(np.int32), 0, 255)
    overlay = cmap_lut[indices].copy()

    nan_mask = np.isnan(vis_data)
    if nan_threshold is not None:
        nan_mask = nan_mask | (vis_data < nan_threshold)
    overlay[..., 3] = np.where(nan_mask, 0, int(alpha * 255)).astype(np.uint8)
    return overlay


def _draw_wind_arrows(
    overlay: np.ndarray,
    u_hi: np.ndarray,
    v_hi: np.ndarray,
    vis_lats: np.ndarray,
    vis_lons: np.ndarray,
) -> np.ndarray:
    """在已有 overlay 上绘制风向箭头（白色半透明）。"""
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
    """向后兼容：风场专用 overlay（风速色斑 + 风向箭头）。"""
    overlay = _build_scalar_overlay(
        vis_speed, 0, max_speed, cmap_lut, alpha=alpha, nan_threshold=0.1
    )
    return _draw_wind_arrows(overlay, u_hi, v_hi, vis_lats, vis_lons)


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


# ── 标量瓦片生成入口 ─────────────────────────────────────────────────
def generate_scalar_tiles(
    data: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    timestamp: str,
    var_cfg: dict,
    output_dir: Path,
    area: dict[str, float] | None = None,
    zoom_levels: range | None = None,
    tile_size: int | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
) -> int:
    """生成标量场透明 XYZ 瓦片（仅数据色斑，无箭头）。

    Args:
        data: 2D (lat × lon) 已转换单位的标量数据
        var_cfg: 来自 config.VARIABLES 的变量配置
        output_dir: 瓦片输出目录
        timestamp: 时间戳字符串
        vmin/vmax: 手动覆盖色阶范围；None 则按 var_cfg['vmin_vmax']

    Returns:
        生成的瓦片总数
    """
    if area is None:
        area = config.DISPLAY_AREA
    if zoom_levels is None:
        zoom_levels = range(config.TILE_ZOOM_MIN, config.TILE_ZOOM_MAX + 1)
    if tile_size is None:
        tile_size = config.TILE_SIZE

    logger.info(f"生成标量瓦片: {timestamp}, 缩放 {zoom_levels.start}-{zoom_levels.stop - 1}")

    vis_data, vis_lats, vis_lons = _smooth_and_interp(data, lat, lon, sigma=1.5)

    # 决定色阶范围
    cfg_range = var_cfg.get("vmin_vmax")
    if vmin is None:
        if cfg_range == "dynamic" or cfg_range is None:
            vmin = float(np.nanmin(vis_data))
        else:
            vmin = cfg_range[0]
    if vmax is None:
        if cfg_range == "dynamic" or cfg_range is None:
            vmax = float(np.nanmax(vis_data))
        else:
            vmax = cfg_range[1]

    cmap_lut = _build_cmap_lut(var_cfg["cmap"])
    overlay = _build_scalar_overlay(vis_data, vmin, vmax, cmap_lut, alpha=0.85)

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


# ── 风场专用瓦片生成入口（向后兼容签名） ─────────────────────────────
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
    """从原始风场数据生成透明 XYZ 瓦片（风速色斑 + 风向箭头）。

    Args:
        output_dir: 瓦片输出目录（必传）

    Returns:
        生成的瓦片总数
    """
    if area is None:
        area = config.DISPLAY_AREA
    if output_dir is None:
        raise ValueError("generate_wind_tiles 需要传入 output_dir")
    if zoom_levels is None:
        zoom_levels = range(config.TILE_ZOOM_MIN, config.TILE_ZOOM_MAX + 1)
    if tile_size is None:
        tile_size = config.TILE_SIZE

    logger.info(f"生成风场瓦片: {timestamp}, 缩放 {zoom_levels.start}-{zoom_levels.stop - 1}")

    vis_speed, u_hi, v_hi, vis_lats, vis_lons, max_speed = _prepare_wind_data(u, v, lat, lon)
    cmap_lut = _build_wind_cmap_lut()
    overlay = _build_overlay(vis_speed, u_hi, v_hi, vis_lats, vis_lons, max_speed, cmap_lut)

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
    particle_dir: Path | None = None,
) -> None:
    """更新瓦片资源清单文件。

    Args:
        datetimes: datetime 对象列表
        manifest_path: 清单文件路径，为 None 时不更新
        particle_dir: 粒子数据目录，为 None 时不记录 particle 信息
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

    # 粒子数据文件列表（仅风场传入 particle_dir）
    if particle_dir is not None:
        particle_files = sorted(
            f.name for f in particle_dir.glob("*.json")
        ) if particle_dir.exists() else []
        manifest["particle"] = {
            "available": len(particle_files) > 0,
            "filenames": particle_files,
        }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    logger.info(f"瓦片清单已更新: {len(merged)} 个时间戳")
