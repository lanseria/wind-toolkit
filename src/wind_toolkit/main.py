"""Wind Toolkit CLI 入口。"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .utils import setup_logger

logger = setup_logger("wind_toolkit.main")


def run_acquisition(forecast_hours: int | None = None) -> list[Path]:
    """执行数据下载阶段。"""
    from .data_acquisition import download_gfs_wind, merge_and_crop

    raw_files = download_gfs_wind(forecast_hours)
    if not raw_files:
        logger.error("未下载到任何数据。")
        return []
    merged = merge_and_crop(raw_files)
    return [merged]


def run_processing(nc_path: Path | None = None) -> list[Path]:
    """执行地图可视化阶段。"""
    from .processor import process_to_textures

    if nc_path is None:
        nc_path = config.PROCESSED_DATA_DIR / "wind_merged.nc"
    if not nc_path.exists():
        logger.error(f"找不到合并数据文件: {nc_path}")
        return []
    return process_to_textures(nc_path)


def run_full_workflow(forecast_hours: int | None = None) -> None:
    """完整流水线: 下载 → 合并裁切 → 地图可视化。"""
    logger.info("=" * 60)
    logger.info("Wind Toolkit 完整流水线启动")

    merged_files = run_acquisition(forecast_hours)
    if not merged_files:
        logger.error("数据获取失败，终止。")
        sys.exit(1)

    nc_path = merged_files[0]
    textures = run_processing(nc_path)
    logger.info(f"流水线完成，共生成 {len(textures)} 张风场地图。")


def _next_gfs_time() -> datetime:
    """计算下一个 GFS 数据可用时间。

    GFS 在 00/06/12/18 UTC 发布，延迟约 GFS_LATENCY_HOURS 后可下载。
    返回下一次应该执行流水线的 UTC 时间。
    """
    now = datetime.now(timezone.utc)
    latency = config.GFS_LATENCY_HOURS

    # 每个周期在 cycle_hour + latency 后可用
    for cycle_hour in config.GFS_CYCLE_HOURS:
        available_at = now.replace(
            hour=cycle_hour, minute=0, second=0, microsecond=0
        ) + timedelta(hours=latency)
        if available_at > now:
            return available_at

    # 今天所有周期都过了，取明天第一个
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(
        hour=config.GFS_CYCLE_HOURS[0], minute=0, second=0, microsecond=0
    ) + timedelta(hours=latency)


def run_scheduled(forecast_hours: int | None = None) -> None:
    """按 GFS 数据发布周期智能调度。

    在每个 GFS 周期数据可用后自动运行流水线（00/06/12/18 UTC + 延迟），
    而非固定间隔轮询。
    """
    logger.info(
        f"GFS 智能调度模式启动，延迟 {config.GFS_LATENCY_HOURS} 小时。按 Ctrl+C 停止。"
    )
    while True:
        next_time = _next_gfs_time()
        now = datetime.now(timezone.utc)
        wait_seconds = (next_time - now).total_seconds()

        beijing_tz = timezone(timedelta(hours=8))
        logger.info(
            f"下次执行: {next_time.astimezone(beijing_tz).strftime('%Y-%m-%d %H:%M')} 北京时间"
            f"（等待 {int(wait_seconds // 60)} 分钟）"
        )

        time.sleep(max(0, wait_seconds))

        try:
            logger.info("----- GFS 数据更新，开始执行 -----")
            run_full_workflow(forecast_hours)
        except Exception as e:
            logger.error(f"流水线异常: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wind Toolkit - GFS 风场地图可视化工具",
    )
    parser.add_argument(
        "--acquire-only", action="store_true", help="仅下载数据"
    )
    parser.add_argument(
        "--process-only", action="store_true", help="仅生成地图（使用已有数据）"
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="按 GFS 数据发布周期智能调度",
    )
    parser.add_argument(
        "--forecast-hours",
        type=int,
        default=config.GFS_FORECAST_HOURS,
        help=f"预报时长（小时），默认 {config.GFS_FORECAST_HOURS}",
    )

    args = parser.parse_args()

    if args.schedule:
        run_scheduled(args.forecast_hours)
    elif args.acquire_only:
        run_acquisition(args.forecast_hours)
    elif args.process_only:
        run_processing()
    else:
        run_full_workflow(args.forecast_hours)


if __name__ == "__main__":
    main()
