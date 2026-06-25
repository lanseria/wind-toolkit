"""Atmos Toolkit 全局配置。"""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np

from dotenv import load_dotenv

# ── 路径 ───────────────────────────────────────────────────────────────
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent  # src/

dotenv_path = PROJECT_ROOT.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)

DATA_DIR: Path = PROJECT_ROOT.parent / "data"
RAW_DATA_DIR: Path = DATA_DIR / "raw"
PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
OUTPUTS_DIR: Path = PROJECT_ROOT.parent / "outputs"
TEXTURES_DIR: Path = OUTPUTS_DIR / "textures"
ATMOS_TILES_ROOT: Path = PROJECT_ROOT.parent / "atmos-tiles"

# ── 等压面层定义 ───────────────────────────────────────────────────────
PRESSURE_LEVELS: list[dict] = [
    {"hpa": 1000, "label": "1000 hPa", "height": "~100 m", "grib_param": "lev_1000_mb"},
    {"hpa": 850,  "label": "850 hPa",  "height": "~1,500 m", "grib_param": "lev_850_mb"},
    {"hpa": 700,  "label": "700 hPa",  "height": "~3,000 m", "grib_param": "lev_700_mb"},
    {"hpa": 500,  "label": "500 hPa",  "height": "~5,500 m", "grib_param": "lev_500_mb"},
    {"hpa": 300,  "label": "300 hPa",  "height": "~9,000 m", "grib_param": "lev_300_mb"},
    {"hpa": 250,  "label": "250 hPa",  "height": "~10,000 m", "grib_param": "lev_250_mb"},
    {"hpa": 200,  "label": "200 hPa",  "height": "~12,000 m", "grib_param": "lev_200_mb"},
    {"hpa": 100,  "label": "100 hPa",  "height": "~16,000 m", "grib_param": "lev_100_mb"},
]


def level_key(hpa: int) -> str:
    return f"{hpa}hPa"


# ── 变量元信息 ─────────────────────────────────────────────────────────
# 单层 GRIB 层级参数映射
# 注意 NOMADS GRIB Filter 中 2m/10m 的层级参数是 `lev_2_m_above_ground`（数字和单位间有下划线）
LEVEL_KEY_MAP: dict[str, str] = {
    "surface": "lev_surface",
    "2m_above_ground": "lev_2_m_above_ground",
    "10m_above_ground": "lev_10_m_above_ground",
    "entire_atmosphere": "lev_entire_atmosphere",
    "mean_sea_level": "lev_mean_sea_level",
}

# 单层虚拟目录 token（用于路径分目录）
SINGLE_LEVEL_KEYS: dict[str, str] = {
    "surface": "surface",
    "2m_above_ground": "2m",
    "10m_above_ground": "10m",
    "entire_atmosphere": "atmos",
    "mean_sea_level": "msl",
}

VARIABLES: dict[str, dict] = {
    # ── 矢量变量（风场，含 U/V 双分量 + 粒子 + 风向箭头） ──
    "wind": {
        "display_name": "Wind Field",
        "grib_vars": ["UGRD", "VGRD"],
        "kind": "vector",
        "nc_names": [["u", "ugrd"], ["v", "vgrd"]],
        "unit": "m/s",
        "level_type": "isobaric",
        "cmap": "wind_speed",
        "vmin_vmax": "dynamic",
        "title_template": "Wind Field {level_label}",
        "generate_particle": True,
        "draw_arrows": True,
    },
    # ── 温度（等压面 + 2m） ──
    "temp": {
        "display_name": "Temperature",
        "grib_vars": ["TMP"],
        "kind": "scalar",
        "nc_names": [["t", "tmp", "t2m", "air_temperature", "temperature"]],
        "unit": "K",
        "unit_display": "°C",
        "convert": "k_to_c",
        "level_type": "both",
        "single_level_key": "2m_above_ground",
        "cmap": "temp",
        "vmin_vmax": (-40, 40),
        "title_template": "Temperature {level_label}",
    },
    # ── 相对湿度（等压面 + 2m） ──
    "rh": {
        "display_name": "Relative Humidity",
        "grib_vars": ["RH"],
        "kind": "scalar",
        "nc_names": [["r", "rh", "r2m", "relative_humidity"]],
        "unit": "%",
        "level_type": "both",
        "single_level_key": "2m_above_ground",
        "cmap": "humidity",
        "vmin_vmax": (0, 100),
        "title_template": "Relative Humidity {level_label}",
    },
    # ── 比湿（等压面 + 2m） ──
    "spfh": {
        "display_name": "Specific Humidity",
        "grib_vars": ["SPFH"],
        "kind": "scalar",
        "nc_names": [["q", "spfh", "q2m", "specific_humidity"]],
        "unit": "kg/kg",
        "unit_display": "g/kg",
        "convert": "kgkg_to_gkg",
        "level_type": "both",
        "single_level_key": "2m_above_ground",
        "cmap": "humidity",
        "vmin_vmax": (0, 20),
        "title_template": "Specific Humidity {level_label}",
    },
    # ── 露点温度（仅 2m，GFS 等压面不发布 DPT） ──
    "dpt": {
        "display_name": "Dew Point",
        "grib_vars": ["DPT"],
        "kind": "scalar",
        "nc_names": [["d", "dpt", "d2m", "dew_point_temperature"]],
        "unit": "K",
        "unit_display": "°C",
        "convert": "k_to_c",
        "level_type": "single",
        "single_level_key": "2m_above_ground",
        "cmap": "temp",
        "vmin_vmax": (-40, 30),
        "title_template": "Dew Point (2m)",
    },
    # ── 位势高度（仅等压面） ──
    "hgt": {
        "display_name": "Geopotential Height",
        "grib_vars": ["HGT"],
        "kind": "scalar",
        "nc_names": [["gh", "hgt", "geopotential_height", "z"]],
        "unit": "m",
        "level_type": "isobaric",
        "cmap": "geo_height",
        "vmin_vmax": "dynamic",
        "title_template": "Geopotential Height {level_label}",
    },
    # ── 总云量（整层大气） ──
    "tcdc": {
        "display_name": "Total Cloud Cover",
        "grib_vars": ["TCDC"],
        "kind": "scalar",
        "nc_names": [["tcc", "tcdc", "total_cloud_cover"]],
        "unit": "%",
        "level_type": "single",
        "single_level_key": "entire_atmosphere",
        "cmap": "cloud",
        "vmin_vmax": (0, 100),
        "title_template": "Total Cloud Cover",
    },
    # ── 低云量 ──
    "lcdc": {
        "display_name": "Low Cloud Cover",
        "grib_vars": ["LCDC"],
        "kind": "scalar",
        "nc_names": [["lcc", "lcdc", "low_cloud_cover"]],
        "unit": "%",
        "level_type": "single",
        "single_level_key": "entire_atmosphere",
        "cmap": "cloud",
        "vmin_vmax": (0, 100),
        "title_template": "Low Cloud Cover",
    },
    # ── 中云量 ──
    "mcdc": {
        "display_name": "Middle Cloud Cover",
        "grib_vars": ["MCDC"],
        "kind": "scalar",
        "nc_names": [["mcc", "mcdc", "middle_cloud_cover"]],
        "unit": "%",
        "level_type": "single",
        "single_level_key": "entire_atmosphere",
        "cmap": "cloud",
        "vmin_vmax": (0, 100),
        "title_template": "Middle Cloud Cover",
    },
    # ── 高云量 ──
    "hcdc": {
        "display_name": "High Cloud Cover",
        "grib_vars": ["HCDC"],
        "kind": "scalar",
        "nc_names": [["hcc", "hcdc", "high_cloud_cover"]],
        "unit": "%",
        "level_type": "single",
        "single_level_key": "entire_atmosphere",
        "cmap": "cloud",
        "vmin_vmax": (0, 100),
        "title_template": "High Cloud Cover",
    },
    # ── 能见度（地表） ──
    "vis": {
        "display_name": "Visibility",
        "grib_vars": ["VIS"],
        "kind": "scalar",
        "nc_names": [["vis", "visibility", "vis_surface"]],
        "unit": "m",
        "unit_display": "km",
        "convert": "m_to_km",
        "level_type": "single",
        "single_level_key": "surface",
        "cmap": "visibility",
        "vmin_vmax": (0, 20),
        "title_template": "Visibility",
    },
    # ── 累计降水（地表） ──
    "apcp": {
        "display_name": "Total Precipitation",
        "grib_vars": ["APCP"],
        "kind": "scalar",
        "nc_names": [["tp", "apcp", "total_precipitation"]],
        "unit": "kg/m^2",
        "unit_display": "mm",
        "level_type": "single",
        "single_level_key": "surface",
        "cmap": "precip",
        "vmin_vmax": (0, 50),
        "title_template": "Total Precipitation",
        "step_type": "avg",
    },
    # ── 降水率（地表） ──
    "prate": {
        "display_name": "Precipitation Rate",
        "grib_vars": ["PRATE"],
        "kind": "scalar",
        "nc_names": [["prate", "precipitation_rate"]],
        "unit": "kg/m^2/s",
        "unit_display": "mm/h",
        "convert": "prate_to_mmh",
        "level_type": "single",
        "single_level_key": "surface",
        "cmap": "precip",
        "vmin_vmax": (0, 30),
        "title_template": "Precipitation Rate",
        "step_type": "avg",
    },
    # ── 地表气压 ──
    "pres": {
        "display_name": "Surface Pressure",
        "grib_vars": ["PRES"],
        "kind": "scalar",
        "nc_names": [["sp", "pres", "surface_pressure", "pressure"]],
        "unit": "Pa",
        "unit_display": "hPa",
        "convert": "pa_to_hpa",
        "level_type": "single",
        "single_level_key": "surface",
        "cmap": "pressure",
        "vmin_vmax": "dynamic",
        "title_template": "Surface Pressure",
    },
    # ── 海平面气压 ──
    "prmsl": {
        "display_name": "Sea Level Pressure",
        "grib_vars": ["PRMSL"],
        "kind": "scalar",
        "nc_names": [["prmsl", "msl", "air_pressure_at_sea_level"]],
        "unit": "Pa",
        "unit_display": "hPa",
        "convert": "pa_to_hpa",
        "level_type": "single",
        "single_level_key": "mean_sea_level",
        "cmap": "pressure",
        "vmin_vmax": "dynamic",
        "title_template": "Sea Level Pressure",
    },
    # ── 地表阵风 ──
    "gust": {
        "display_name": "Wind Gust",
        "grib_vars": ["GUST"],
        "kind": "scalar",
        "nc_names": [["gust", "wind_speed_of_gust", "gusts"]],
        "unit": "m/s",
        "level_type": "single",
        "single_level_key": "surface",
        "cmap": "wind_speed",
        "vmin_vmax": (0, 50),
        "title_template": "Wind Gust",
    },
}


def level_grib_param(var_cfg: dict, hpa: int | None) -> str:
    """根据变量配置 + hPa，返回该 (variable, level) 组合的 NOMADS lev_xxx。"""
    if var_cfg["level_type"] in ("isobaric", "both") and hpa is not None:
        return next(lv["grib_param"] for lv in PRESSURE_LEVELS if lv["hpa"] == hpa)
    return LEVEL_KEY_MAP[var_cfg["single_level_key"]]


def _level_token(hpa: int | None, single_level_key: str | None) -> str:
    """统一层级目录 token（等压面或单层虚拟 token）。"""
    if hpa is not None:
        return level_key(hpa)
    if single_level_key is None:
        return "default"
    return SINGLE_LEVEL_KEYS.get(single_level_key, single_level_key)


# ── 通用路径函数（按 variable + level 寻址） ─────────────────────────
def tile_dir_for(
    var_name: str, hpa: int | None = None, single_level_key: str | None = None
) -> Path:
    """瓦片目录：atmos-tiles/{variable}/{level_token}/"""
    var_cfg = VARIABLES[var_name]
    sk = single_level_key or var_cfg.get("single_level_key")
    return ATMOS_TILES_ROOT / var_name / _level_token(hpa, sk)


def tile_manifest_for(
    var_name: str, hpa: int | None = None, single_level_key: str | None = None
) -> Path:
    return tile_dir_for(var_name, hpa, single_level_key) / "tiles_manifest.json"


def textures_dir_for(
    var_name: str, hpa: int | None = None, single_level_key: str | None = None
) -> Path:
    """纹理 PNG 目录：outputs/textures/{variable}/{level_token}/"""
    var_cfg = VARIABLES[var_name]
    sk = single_level_key or var_cfg.get("single_level_key")
    return TEXTURES_DIR / var_name / _level_token(hpa, sk)


def raw_data_dir_for(
    var_name: str, hpa: int | None = None, single_level_key: str | None = None
) -> Path:
    """原始 GRIB2 目录：data/raw/{variable}/{level_token}/"""
    var_cfg = VARIABLES[var_name]
    sk = single_level_key or var_cfg.get("single_level_key")
    return RAW_DATA_DIR / var_name / _level_token(hpa, sk)


def processed_data_dir_for(
    var_name: str, hpa: int | None = None, single_level_key: str | None = None
) -> Path:
    """处理后 NetCDF 目录：data/processed/{variable}/{level_token}/"""
    var_cfg = VARIABLES[var_name]
    sk = single_level_key or var_cfg.get("single_level_key")
    return PROCESSED_DATA_DIR / var_name / _level_token(hpa, sk)


def particle_data_dir_for(
    var_name: str, hpa: int | None = None, single_level_key: str | None = None
) -> Path | None:
    """粒子数据目录，仅风场返回路径，其他变量返回 None。"""
    if var_name != "wind":
        return None
    return tile_dir_for(var_name, hpa, single_level_key) / "particle"


# ── 向后兼容：旧等压面分目录函数（仅适用 wind） ─────────────────────
def tile_dir_for_level(hpa: int) -> Path:
    return tile_dir_for("wind", hpa=hpa)


def tile_manifest_for_level(hpa: int) -> Path:
    return tile_manifest_for("wind", hpa=hpa)


def textures_dir_for_level(hpa: int) -> Path:
    return textures_dir_for("wind", hpa=hpa)


def raw_data_dir_for_level(hpa: int) -> Path:
    return raw_data_dir_for("wind", hpa=hpa)


def processed_data_dir_for_level(hpa: int) -> Path:
    return processed_data_dir_for("wind", hpa=hpa)


def particle_data_dir_for_level(hpa: int) -> Path:
    return particle_data_dir_for("wind", hpa=hpa)  # type: ignore[return-value]


for _d in (RAW_DATA_DIR, PROCESSED_DATA_DIR, TEXTURES_DIR, ATMOS_TILES_ROOT):
    _d.mkdir(parents=True, exist_ok=True)

# ── GFS 数据源 ─────────────────────────────────────────────────────────
GFS_URL_BASE: str = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
GFS_RESOLUTION: float = 0.25
GFS_CYCLE_HOURS: list[int] = [0, 6, 12, 18]  # UTC
GFS_LATENCY_HOURS: int = int(os.getenv("GFS_LATENCY_HOURS", "4"))
GFS_FORECAST_HOURS: int = int(os.getenv("GFS_FORECAST_HOURS", "24"))

# ── 地理范围 ───────────────────────────────────────────────────────────
# 全球覆盖：南纬 90° 到北纬 90°，经度 -180° 到 180°
DISPLAY_AREA: dict[str, float] = {
    "north": 90.0,
    "south": -90.0,
    "west": -180.0,
    "east": 180.0,
}

# 下载区域缓冲（全球覆盖时缓冲自动被 clamp 到地球边界，等同于 DISPLAY_AREA）
BUFFER_DEGREES: float = 5.0
DOWNLOAD_AREA: dict[str, float] = {
    "north": min(90.0, DISPLAY_AREA["north"] + BUFFER_DEGREES),
    "south": max(-90.0, DISPLAY_AREA["south"] - BUFFER_DEGREES),
    "west": max(-180.0, DISPLAY_AREA["west"] - BUFFER_DEGREES),
    "east": min(180.0, DISPLAY_AREA["east"] + BUFFER_DEGREES),
}

# ── 时间配置 ───────────────────────────────────────────────────────────
BEIJING_TZ = timezone(timedelta(hours=8))
UTC = timezone.utc

# ── 地图可视化 ─────────────────────────────────────────────────────────
# 地图数据路径（支持环境变量覆盖，Docker 部署时设为 /app）
_MAP_DATA_ROOT: Path = Path(
    os.environ.get("MAP_DATA_ROOT", str(PROJECT_ROOT.parent.parent / "chromasky-toolkit"))
)
MAP_DATA_DIR: Path = _MAP_DATA_ROOT / "map_data"
FONT_DIR: Path = _MAP_DATA_ROOT / "fonts"
CHINA_SHP_PATH: Path = MAP_DATA_DIR / "china.shp"
NINE_DASH_LINE_SHP_PATH: Path = MAP_DATA_DIR / "china_nine_dotted_line.shp"
CITIES_CSV_PATH: Path = MAP_DATA_DIR / "china_cities.csv"
FONT_FILENAME: str = "LXGWWenKai-Regular.ttf"
FONT_NAME: str = "LXGW WenKai"

# ── Colormap 配置（7 种共享色阶） ─────────────────────────────────────
COLORMAPS: dict[str, dict] = {
    "wind_speed": {  # 深蓝→青→绿→黄→橙→红
        "colors": [
            "#1a1a2e", "#16537e", "#0096c7", "#00b4d8", "#48cae4",
            "#90e0ef", "#caffbf", "#fdffb6", "#ffd166", "#f4845f",
            "#d62828", "#9d0208",
        ],
        "nodes": [0.0, 0.04, 0.10, 0.18, 0.26, 0.35, 0.48, 0.60, 0.72, 0.85, 0.93, 1.0],
    },
    "temp": {  # 深蓝→蓝→青→黄→橙→深红
        "colors": [
            "#1e3a8a", "#3b82f6", "#06b6d4", "#22d3ee", "#a3e635",
            "#fde047", "#fb923c", "#ef4444", "#7f1d1d",
        ],
        "nodes": [0.0, 0.12, 0.25, 0.4, 0.55, 0.68, 0.8, 0.92, 1.0],
    },
    "humidity": {  # 浅黄（干）→绿→青蓝→深蓝（湿）
        "colors": [
            "#fef3c7", "#fde68a", "#86efac", "#22d3ee",
            "#0284c7", "#1e3a8a", "#0c1e4f",
        ],
        "nodes": [0.0, 0.15, 0.35, 0.55, 0.75, 0.9, 1.0],
    },
    "cloud": {  # 暗黑→浅灰→白
        "colors": ["#0c0a09", "#3b3a36", "#78716c", "#a8a29e", "#d6d3d1", "#f5f5f4"],
        "nodes": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
    },
    "precip": {  # 暗黑→浅蓝→深蓝→紫（强降水）
        "colors": [
            "#0c0a09", "#0891b2", "#06b6d4", "#67e8f9",
            "#a78bfa", "#7c3aed", "#4c1d95",
        ],
        "nodes": [0.0, 0.1, 0.25, 0.45, 0.7, 0.88, 1.0],
    },
    "visibility": {  # 红（差）→黄→绿（好）
        "colors": [
            "#7f1d1d", "#dc2626", "#fb923c", "#fde047",
            "#a3e635", "#22c55e", "#15803d",
        ],
        "nodes": [0.0, 0.15, 0.3, 0.45, 0.6, 0.8, 1.0],
    },
    "pressure": {  # 低（蓝紫）→高（红橙）
        "colors": [
            "#312e81", "#1e40af", "#0284c7", "#67e8f9",
            "#fde047", "#fb923c", "#dc2626",
        ],
        "nodes": [0.0, 0.15, 0.3, 0.5, 0.7, 0.85, 1.0],
    },
    "geo_height": {  # 深紫→蓝→青→绿→黄
        "colors": [
            "#1e1b4b", "#3730a3", "#1d4ed8", "#0891b2",
            "#10b981", "#fde047", "#f59e0b",
        ],
        "nodes": [0.0, 0.15, 0.3, 0.5, 0.7, 0.88, 1.0],
    },
}

# 向后兼容：保留旧引用
WIND_COLORS: list[str] = COLORMAPS["wind_speed"]["colors"]
WIND_COLOR_NODES: list[float] = COLORMAPS["wind_speed"]["nodes"]


# ── 单位转换 ───────────────────────────────────────────────────────────
def _k_to_c(a: np.ndarray) -> np.ndarray:
    return a - 273.15


def _kgkg_to_gkg(a: np.ndarray) -> np.ndarray:
    return a * 1000.0


def _m_to_km(a: np.ndarray) -> np.ndarray:
    return a / 1000.0


def _prate_to_mmh(a: np.ndarray) -> np.ndarray:
    return a * 3600.0


def _pa_to_hpa(a: np.ndarray) -> np.ndarray:
    return a / 100.0


def _identity(a: np.ndarray) -> np.ndarray:
    return a


UNIT_CONVERTERS: dict[str, callable] = {
    "k_to_c": _k_to_c,
    "kgkg_to_gkg": _kgkg_to_gkg,
    "m_to_km": _m_to_km,
    "prate_to_mmh": _prate_to_mmh,
    "pa_to_hpa": _pa_to_hpa,
}


def apply_unit_convert(data: np.ndarray, var_cfg: dict) -> np.ndarray:
    """按 var_cfg['convert'] 应用单位转换，未配置则原样返回。"""
    fn = UNIT_CONVERTERS.get(var_cfg.get("convert", ""), _identity)
    return fn(data)


# ── 瓦片 ───────────────────────────────────────────────────────────────
TILE_ZOOM_MIN: int = 3
TILE_ZOOM_MAX: int = 4
TILE_SIZE: int = 256

# ── 并行 ───────────────────────────────────────────────────────────────
NUM_WORKERS: int = int(
    os.getenv("NUM_WORKERS", max(1, (os.cpu_count() or 1) // 2))
)
