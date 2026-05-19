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
TILE_OUTPUT_DIR: Path = PROJECT_ROOT.parent / "wind-tiles"
TILE_MANIFEST_PATH: Path = TILE_OUTPUT_DIR / "tiles_manifest.json"

for _d in (RAW_DATA_DIR, PROCESSED_DATA_DIR, TEXTURES_DIR, TILE_OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── GFS 数据源 ─────────────────────────────────────────────────────────
GFS_URL_BASE: str = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
GFS_RESOLUTION: float = 0.25
GFS_CYCLE_HOURS: list[int] = [0, 6, 12, 18]  # UTC
GFS_LATENCY_HOURS: int = int(os.getenv("GFS_LATENCY_HOURS", "4"))
GFS_FORECAST_HOURS: int = int(os.getenv("GFS_FORECAST_HOURS", "24"))

# ── 地理范围 ───────────────────────────────────────────────────────────
DISPLAY_AREA: dict[str, float] = {
    "north": 54.0,
    "south": 0.0,
    "west": 70.0,
    "east": 135.0,
}

BUFFER_DEGREES: float = 5.0
DOWNLOAD_AREA: dict[str, float] = {
    "north": DISPLAY_AREA["north"] + BUFFER_DEGREES,
    "south": DISPLAY_AREA["south"] - BUFFER_DEGREES,
    "west": DISPLAY_AREA["west"] - BUFFER_DEGREES,
    "east": DISPLAY_AREA["east"] + BUFFER_DEGREES,
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
