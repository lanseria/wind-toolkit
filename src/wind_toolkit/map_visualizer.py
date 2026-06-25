"""气象变量地图可视化模块。

提供暗色主题地图渲染，支持任意标量气象变量（温度/湿度/云量/降水/能见度/气压等）
和风场专用渲染（含风向箭头）。
"""

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

logger = setup_logger("atmos_toolkit.visualizer")

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


# ── 通用辅助函数 ──────────────────────────────────────────────────────
def _build_colormap(cmap_name: str) -> mcolors.LinearSegmentedColormap:
    """根据 config.COLORMAPS 名称构建 colormap。"""
    spec = config.COLORMAPS[cmap_name]
    return mcolors.LinearSegmentedColormap.from_list(
        cmap_name, list(zip(spec["nodes"], spec["colors"]))
    )


def _build_wind_cmap() -> mcolors.LinearSegmentedColormap:
    """向后兼容：风速专用 colormap。"""
    return _build_colormap("wind_speed")


def _smooth_and_interpolate(
    data: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    sigma: float = 1.5,
    interp_factor: int = 4,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """高斯平滑 + 4x 三次插值。

    Returns:
        (hi_data, new_lats, new_lons)
    """
    da = xr.DataArray(
        data,
        coords={"latitude": lat, "longitude": lon},
        dims=["latitude", "longitude"],
    )
    if sigma > 0:
        smoothed = gaussian_filter(da.fillna(0).values, sigma=sigma)
        da = xr.DataArray(smoothed, coords=da.coords, dims=da.dims)
    new_lats = np.linspace(lat.min(), lat.max(), len(lat) * interp_factor)
    new_lons = np.linspace(lon.min(), lon.max(), len(lon) * interp_factor)
    hi = da.interp(latitude=new_lats, longitude=new_lons, method="cubic")
    return hi.values, new_lats, new_lons


def _setup_axes(figsize: tuple[float, float] = (12, 10)):
    """创建暗色主题 cartopy PlateCarree axes。Returns: (fig, ax, proj)"""
    proj = ccrs.PlateCarree()
    fig = plt.figure(figsize=figsize, facecolor="black")
    ax = fig.add_subplot(1, 1, 1, projection=proj)
    ax.set_facecolor("black")

    display = config.DISPLAY_AREA
    ax.set_extent(
        [display["west"], display["east"], display["south"], display["north"]],
        crs=proj,
    )

    ax.add_feature(
        cfeature.OCEAN.with_scale("50m"), facecolor="#0c0a09", zorder=0
    )
    ax.add_feature(
        cfeature.LAND.with_scale("50m"), facecolor="#1c1917", edgecolor="none", zorder=0
    )
    return fig, ax, proj


def _draw_geopolitical(ax, proj) -> None:
    """添加中国国界、九段线、海岸线。"""
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


def _draw_gridlines(ax) -> None:
    """添加经纬度网格线（隐藏顶部和右侧标签）。"""
    gl = ax.gridlines(
        draw_labels=True, linewidth=0.5,
        color="#44403c", alpha=0.8, linestyle="--",
    )
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = {"color": "white", "size": 10}
    gl.ylabel_style = {"color": "white", "size": 10}


def _draw_title(ax, title_text: str, timestamp: datetime) -> None:
    """绘制 UTC/BJT 双时区标题。title_text 为主标题前缀（如 'Wind Field 850 hPa'）。"""
    t_str = timestamp.strftime("%Y-%m-%d %H:%M UTC")
    bj_str = timestamp.astimezone(config.BEIJING_TZ).strftime("%Y-%m-%d %H:%M BJT")
    ax.set_title(
        f"{title_text} - {t_str} ({bj_str})",
        fontsize=16, color="white", pad=20,
    )


def _save_fig(fig, output_path: Path) -> None:
    """保存 PNG 到 output_path。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(
        output_path, format="png", dpi=150,
        bbox_inches="tight", pad_inches=0.1,
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)


def _add_colorbar(fig, cf, label_text: str) -> None:
    """添加暗色主题 colorbar。"""
    cbar = fig.colorbar(cf, ax=fig.axes[0], orientation="vertical", pad=0.02, shrink=0.8)
    cbar.set_label(label_text, color="white", fontsize=12)
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")


# ── 标量场渲染（温度/湿度/云量/降水/能见度/气压/HGT/GUST 等） ────────
def generate_scalar_map(
    data: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    timestamp: datetime,
    output_path: Path,
    var_cfg: dict,
    level_label: str | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
) -> Path:
    """生成标量场暗色主题地图。

    Args:
        data: 2D (lat × lon) 已转换单位的标量数据
        var_cfg: 来自 config.VARIABLES 的变量配置
        level_label: 层级标注（如 "850 hPa (~1,500 m)" 或 "2m"），可选
        vmin/vmax: 手动覆盖色阶范围；None 则按 var_cfg['vmin_vmax']
    """
    hi_data, vis_lats, vis_lons = _smooth_and_interpolate(data, lat, lon)

    # 决定色阶范围
    cfg_range = var_cfg.get("vmin_vmax")
    if vmin is None:
        if cfg_range == "dynamic" or cfg_range is None:
            vmin = float(np.nanmin(hi_data))
        else:
            vmin = cfg_range[0]
    if vmax is None:
        if cfg_range == "dynamic" or cfg_range is None:
            vmax = float(np.nanmax(hi_data))
        else:
            vmax = cfg_range[1]

    fig, ax, proj = _setup_axes()
    cmap = _build_colormap(var_cfg["cmap"])
    levels = np.linspace(vmin, vmax, 50)
    cf = ax.contourf(
        vis_lons, vis_lats, hi_data,
        levels=levels, cmap=cmap, transform=proj, extend="both", zorder=1,
    )

    unit = var_cfg.get("unit_display", var_cfg.get("unit", ""))
    _add_colorbar(fig, cf, f"{var_cfg['display_name']} ({unit})")

    _draw_geopolitical(ax, proj)
    _draw_gridlines(ax)

    title = var_cfg["title_template"].format(
        level_label=f"({level_label})" if level_label else ""
    ).strip()
    # 去掉可能的多余空格（level_label 为空时 "Temperature " → "Temperature"）
    title = " ".join(title.split())
    _draw_title(ax, title, timestamp)
    _save_fig(fig, output_path)
    return output_path


# ── 风场专用渲染（含风速色斑 + quiver 风向箭头） ─────────────────────
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

    # 风速做高斯平滑 + 插值（视觉增强）
    vis_speed, vis_lats, vis_lons = _smooth_and_interpolate(speed, lat, lon)
    # U/V 只插值不平滑，保留细节用于箭头
    u_hi, _, _ = _smooth_and_interpolate(u, lat, lon, sigma=0)
    v_hi, _, _ = _smooth_and_interpolate(v, lat, lon, sigma=0)

    fig, ax, proj = _setup_axes()

    cmap = _build_colormap("wind_speed")
    levels = np.linspace(0, max_speed, 50)
    cf = ax.contourf(
        vis_lons, vis_lats, vis_speed,
        levels=levels, cmap=cmap, transform=proj, extend="max", zorder=1,
    )
    _add_colorbar(fig, cf, "Wind Speed (m/s)")

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

    _draw_geopolitical(ax, proj)
    _draw_gridlines(ax)

    prefix = f"Wind Field {level_label}" if level_label else "Wind Field"
    _draw_title(ax, prefix, timestamp)
    _save_fig(fig, output_path)
    return output_path
