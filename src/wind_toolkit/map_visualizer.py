"""风场地图可视化模块。"""

import io
from datetime import datetime
from pathlib import Path

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import numpy as np
import xarray as xr
from cartopy.io import shapereader
from scipy.ndimage import gaussian_filter

from . import config
from .utils import setup_logger

logger = setup_logger("wind_toolkit.visualizer")

# ── 字体设置 ──────────────────────────────────────────────────────────
CHINESE_FONT_FOUND = False
_font_properties: fm.FontProperties | None = None
try:
    custom_font = config.FONT_DIR / config.FONT_FILENAME
    if custom_font.exists():
        fm.fontManager.addfont(str(custom_font))
        plt.rcParams["font.sans-serif"] = [config.FONT_NAME]
        _font_properties = fm.FontProperties(fname=str(custom_font))
        CHINESE_FONT_FOUND = True
        logger.info(f"加载字体: {custom_font}")
    else:
        # 扫描系统中文字体
        for font in fm.FontManager().ttflist:
            if any(
                kw in font.name
                for kw in [
                    "SimHei", "Microsoft YaHei", "PingFang SC",
                    "Noto Sans CJK SC", "WenQuanYi",
                ]
            ):
                plt.rcParams["font.sans-serif"] = [font.name]
                _font_properties = fm.FontProperties(name=font.name)
                CHINESE_FONT_FOUND = True
                logger.info(f"使用系统字体: {font.name}")
                break
    plt.rcParams["axes.unicode_minus"] = False
except Exception as e:
    logger.warning(f"字体设置异常: {e}")


def _build_wind_cmap() -> mcolors.LinearSegmentedColormap:
    """构建风速专用 colormap。"""
    return mcolors.LinearSegmentedColormap.from_list(
        "wind_speed",
        list(zip(config.WIND_COLOR_NODES, config.WIND_COLORS)),
    )


def generate_wind_map(
    u: np.ndarray,
    v: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    timestamp: datetime,
    output_path: Path,
    level_label: str | None = None,
) -> Path:
    """生成风场暗色主题地图。

    Args:
        u: 2D U 分量 (lat × lon)
        v: 2D V 分量 (lat × lon)
        lat: 1D 纬度数组
        lon: 1D 经度数组
        timestamp: 该帧时间
        output_path: 输出 PNG 路径
    """
    speed = np.sqrt(u**2 + v**2)
    max_speed = float(np.nanmax(speed)) if not np.all(np.isnan(speed)) else 20.0

    # ── 数据平滑与插值（复用 chromasky 的视觉增强）─────────────────
    interp_factor = 4
    speed_da = xr.DataArray(
        speed,
        coords={"latitude": lat, "longitude": lon},
        dims=["latitude", "longitude"],
    )
    smoothed = gaussian_filter(speed_da.fillna(0).values, sigma=1.5)
    smoothed_da = xr.DataArray(
        smoothed, coords=speed_da.coords, dims=speed_da.dims
    )
    new_lats = np.linspace(lat.min(), lat.max(), len(lat) * interp_factor)
    new_lons = np.linspace(lon.min(), lon.max(), len(lon) * interp_factor)
    hi_res = smoothed_da.interp(
        latitude=new_lats, longitude=new_lons, method="cubic"
    )
    vis_speed = hi_res.values

    # 同样对 U/V 做插值（用于箭头）
    u_da = xr.DataArray(u, coords={"latitude": lat, "longitude": lon}, dims=["latitude", "longitude"])
    v_da = xr.DataArray(v, coords={"latitude": lat, "longitude": lon}, dims=["latitude", "longitude"])
    u_hi = u_da.interp(latitude=new_lats, longitude=new_lons, method="cubic").values
    v_hi = v_da.interp(latitude=new_lats, longitude=new_lons, method="cubic").values

    vis_lats = new_lats
    vis_lons = new_lons

    # ── 绘图 ────────────────────────────────────────────────────────
    proj = ccrs.PlateCarree()
    fig = plt.figure(figsize=(12, 10), facecolor="black")
    ax = fig.add_subplot(1, 1, 1, projection=proj)
    ax.set_facecolor("black")

    display = config.DISPLAY_AREA
    ax.set_extent(
        [display["west"], display["east"], display["south"], display["north"]],
        crs=proj,
    )

    # 底图
    ax.add_feature(
        cfeature.OCEAN.with_scale("50m"), facecolor="#0c0a09", zorder=0
    )
    ax.add_feature(
        cfeature.LAND.with_scale("50m"), facecolor="#1c1917", edgecolor="none", zorder=0
    )

    # 风速色斑
    cmap = _build_wind_cmap()
    levels = np.linspace(0, max_speed, 50)
    cf = ax.contourf(
        vis_lons,
        vis_lats,
        vis_speed,
        levels=levels,
        cmap=cmap,
        transform=proj,
        extend="max",
        zorder=1,
    )

    # colorbar
    cbar = fig.colorbar(cf, ax=ax, orientation="vertical", pad=0.02, shrink=0.8)
    cbar.set_label("Wind Speed (m/s)", color="white", fontsize=12)
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")

    # 风向箭头（精细稀疏采样）
    skip_lat = max(1, len(vis_lats) // 30)
    skip_lon = max(1, len(vis_lons) // 30)
    ax.quiver(
        vis_lons[::skip_lon],
        vis_lats[::skip_lat],
        u_hi[::skip_lat, ::skip_lon],
        v_hi[::skip_lat, ::skip_lon],
        color="white",
        alpha=0.5,
        scale=250,
        width=0.002,
        headwidth=3,
        headlength=4,
        transform=proj,
        zorder=5,
    )

    # 国界和九段线
    if config.CHINA_SHP_PATH.exists():
        ax.add_geometries(
            shapereader.Reader(str(config.CHINA_SHP_PATH)).geometries(),
            proj,
            facecolor="none",
            edgecolor="#a8a29e",
            linewidth=0.5,
            zorder=2,
        )
    if config.NINE_DASH_LINE_SHP_PATH.exists():
        ax.add_geometries(
            shapereader.Reader(str(config.NINE_DASH_LINE_SHP_PATH)).geometries(),
            proj,
            facecolor="none",
            edgecolor="#a8a29e",
            linewidth=1.0,
            zorder=2,
        )
    ax.add_feature(
        cfeature.COASTLINE.with_scale("50m"),
        edgecolor="#78716c",
        linewidth=0.5,
        zorder=2,
    )

    # 网格线
    gl = ax.gridlines(
        draw_labels=True, linewidth=0.5,
        color="#44403c", alpha=0.8, linestyle="--",
    )
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = {"color": "white", "size": 10}
    gl.ylabel_style = {"color": "white", "size": 10}

    # 标题
    t_str = timestamp.strftime("%Y-%m-%d %H:%M UTC")
    bj_str = timestamp.astimezone(config.BEIJING_TZ).strftime("%Y-%m-%d %H:%M BJT")
    prefix = f"Wind Field {level_label} - " if level_label else "Wind Field - "
    ax.set_title(
        f"{prefix}{t_str} ({bj_str})",
        fontsize=16, color="white", pad=20,
    )

    # 保存
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(
        output_path, format="png", dpi=150,
        bbox_inches="tight", pad_inches=0.1,
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)

    return output_path
