"""Wind Toolkit 全局配置。"""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

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
WIND_TILES_ROOT: Path = PROJECT_ROOT.parent / "wind-tiles"

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


def tile_dir_for_level(hpa: int) -> Path:
    return WIND_TILES_ROOT / level_key(hpa)


def tile_manifest_for_level(hpa: int) -> Path:
    return tile_dir_for_level(hpa) / "tiles_manifest.json"


def textures_dir_for_level(hpa: int) -> Path:
    return TEXTURES_DIR / level_key(hpa)


def raw_data_dir_for_level(hpa: int) -> Path:
    return RAW_DATA_DIR / level_key(hpa)


def processed_data_dir_for_level(hpa: int) -> Path:
    return PROCESSED_DATA_DIR / level_key(hpa)


def particle_data_dir_for_level(hpa: int) -> Path:
    """粒子风场 JSON 数据目录。"""
    return tile_dir_for_level(hpa) / "particle"

for _d in (RAW_DATA_DIR, PROCESSED_DATA_DIR, TEXTURES_DIR, WIND_TILES_ROOT):
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

# 风速 colormap
WIND_COLORS: list[str] = [
    "#1a1a2e", "#16537e", "#0096c7", "#00b4d8", "#48cae4",
    "#90e0ef", "#caffbf", "#fdffb6", "#ffd166", "#f4845f",
    "#d62828", "#9d0208",
]
WIND_COLOR_NODES: list[float] = [
    0.0, 0.04, 0.10, 0.18, 0.26,
    0.35, 0.48, 0.60, 0.72, 0.85,
    0.93, 1.0,
]

# ── 瓦片 ───────────────────────────────────────────────────────────────
TILE_ZOOM_MIN: int = 3
TILE_ZOOM_MAX: int = 8
TILE_SIZE: int = 256

# ── 并行 ───────────────────────────────────────────────────────────────
NUM_WORKERS: int = int(
    os.getenv("NUM_WORKERS", max(1, (os.cpu_count() or 1) // 2))
)
