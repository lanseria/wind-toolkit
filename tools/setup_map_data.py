# tools/setup_map_data.py

"""构建时下载地图数据和字体，Docker 部署使用。"""

import logging
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atmos_toolkit import config

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("DataSetup")

# --- 地图数据配置 ---
MAP_DATA_URL = "https://ghfast.top/https://github.com/Supeset/China-GeoData/archive/refs/heads/master.zip"

# --- 字体数据配置 ---
FONT_BASE_URL = "https://ghfast.top/https://github.com/lxgw/LxgwWenKai/raw/main/fonts/TTF/"
FONT_FILENAMES = ["LXGWWenKai-Regular.ttf"]


def setup_font_data():
    """下载 LXGW WenKai 字体（幂等）。"""
    logger.info("===== 开始下载字体 =====")
    config.FONT_DIR.mkdir(parents=True, exist_ok=True)

    if all((config.FONT_DIR / f).exists() for f in FONT_FILENAMES):
        logger.info("字体文件已存在，跳过下载。")
        return

    for filename in FONT_FILENAMES:
        target = config.FONT_DIR / filename
        if target.exists():
            continue
        url = FONT_BASE_URL + filename
        try:
            logger.info(f"  下载字体: {url}")
            urllib.request.urlretrieve(url, target)
        except Exception as e:
            logger.error(f"  下载失败: {filename} - {e}")

    logger.info("===== 字体设置完成 =====")


def setup_map_data():
    """下载中国地图 shapefile（幂等）。"""
    logger.info("===== 开始下载地图数据 =====")
    config.MAP_DATA_DIR.mkdir(parents=True, exist_ok=True)

    required_files = [config.CHINA_SHP_PATH, config.NINE_DASH_LINE_SHP_PATH]
    if all(f.exists() for f in required_files):
        logger.info("地图数据已存在，跳过下载。")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        zip_path = tmp_path / "china-geodata.zip"

        try:
            logger.info(f"下载地图数据: {MAP_DATA_URL}")
            urllib.request.urlretrieve(MAP_DATA_URL, zip_path)
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return

        extract_path = tmp_path / "extracted"
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_path)
        except Exception as e:
            logger.error(f"解压失败: {e}")
            return

        repo_dir = next(extract_path.glob("China-GeoData-*"), None)
        if not repo_dir:
            logger.error("未找到 China-GeoData 目录。")
            return

        source_shp = repo_dir / "shp"
        if source_shp.exists():
            for f in source_shp.glob("*"):
                shutil.move(str(f), str(config.MAP_DATA_DIR / f.name))
            logger.info(f"已移动 shapefile 到 {config.MAP_DATA_DIR}")

    logger.info("===== 地图数据设置完成 =====")


if __name__ == "__main__":
    setup_map_data()
    setup_font_data()
