"""Wind Toolkit CLI 入口。"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .utils import setup_logger

logger = setup_logger("wind_toolkit.main")


def _get_levels(level_hpa: int | None = None) -> list[dict]:
    """获取要处理的等压面层列表。"""
    if level_hpa is not None:
        for lv in config.PRESSURE_LEVELS:
            if lv["hpa"] == level_hpa:
                return [lv]
        logger.error(f"未知等压面层: {level_hpa} hPa")
        logger.info(f"可用层: {', '.join(str(lv['hpa']) for lv in config.PRESSURE_LEVELS)}")
        sys.exit(1)
    return config.PRESSURE_LEVELS


def run_acquisition(forecast_hours: int | None = None, level_hpa: int | None = None) -> list[Path]:
    """执行数据下载阶段。"""
    from .data_acquisition import download_gfs_wind, merge_and_crop

    levels = _get_levels(level_hpa)
    merged_files: list[Path] = []

    for level in levels:
        logger.info(f"========== {level['label']} ({level['height']}) ==========")
        raw_files = download_gfs_wind(level, forecast_hours)
        if not raw_files:
            logger.warning(f"[{level['label']}] 未下载到任何数据。")
            continue
        merged = merge_and_crop(raw_files, level)
        merged_files.append(merged)

    return merged_files


def run_processing(level_hpa: int | None = None) -> list[Path]:
    """执行地图可视化阶段。"""
    from .processor import process_to_textures

    levels = _get_levels(level_hpa)
    all_outputs: list[Path] = []

    for level in levels:
        nc_path = config.processed_data_dir_for_level(level["hpa"]) / "wind_merged.nc"
        if not nc_path.exists():
            logger.warning(f"[{level['label']}] 找不到数据文件: {nc_path}")
            continue
        outputs = process_to_textures(nc_path, level)
        all_outputs.extend(outputs)

    return all_outputs


def run_full_workflow(forecast_hours: int | None = None, level_hpa: int | None = None) -> None:
    """完整流水线: 下载 → 合并裁切 → 地图可视化。"""
    logger.info("=" * 60)
    logger.info("Wind Toolkit 完整流水线启动")

    merged_files = run_acquisition(forecast_hours, level_hpa)
    if not merged_files:
        logger.error("数据获取失败，终止。")
        sys.exit(1)

    run_processing(level_hpa)
    logger.info("流水线完成。")


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
    而非固定间隔轮询。仅处理 850 hPa 层。
    """
    level_hpa = 850
    logger.info(
        f"GFS 智能调度模式启动，仅处理 {level_hpa} hPa 层，"
        f"延迟 {config.GFS_LATENCY_HOURS} 小时。按 Ctrl+C 停止。"
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
            run_full_workflow(forecast_hours, level_hpa)
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
    parser.add_argument(
        "--level",
        type=int,
        default=None,
        help=f"指定等压面层（hPa），如 850。默认处理所有层: {', '.join(str(l['hpa']) for l in config.PRESSURE_LEVELS)}",
    )

    args = parser.parse_args()

    if args.schedule:
        run_scheduled(args.forecast_hours)
    elif args.acquire_only:
        run_acquisition(args.forecast_hours, args.level)
    elif args.process_only:
        run_processing(args.level)
    else:
        run_full_workflow(args.forecast_hours, args.level)


if __name__ == "__main__":
    main()
