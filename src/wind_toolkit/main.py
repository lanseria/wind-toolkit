"""Atmos Toolkit CLI 入口。

支持多气象变量（wind/temp/rh/spfh/dpt/hgt/tcdc/lcdc/mcdc/hcdc/vis/apcp/prate/pres/prmsl/gust）。
通过 `--variable/-v` 指定单变量，`--variables` 多变量，`--all-variables` 全部。
默认行为保持 wind（与旧版本兼容）。
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .utils import setup_logger

logger = setup_logger("atmos_toolkit.main")


def _get_levels(level_hpa: int | None = None) -> list[dict]:
    """获取要处理的等压面层列表（仅 wind 兼容入口）。"""
    if level_hpa is not None:
        for lv in config.PRESSURE_LEVELS:
            if lv["hpa"] == level_hpa:
                return [lv]
        logger.error(f"未知等压面层: {level_hpa} hPa")
        logger.info(f"可用层: {', '.join(str(lv['hpa']) for lv in config.PRESSURE_LEVELS)}")
        sys.exit(1)
    return config.PRESSURE_LEVELS


def _resolve_var_names(args) -> list[str]:
    """从 CLI 参数解析变量名列表。"""
    if getattr(args, "all_variables", False):
        return list(config.VARIABLES.keys())
    if getattr(args, "variables", None):
        return _validate_var_names(args.variables)
    if getattr(args, "variable", None):
        return _validate_var_names([args.variable])
    return ["wind"]


def _validate_var_names(names: list[str]) -> list[str]:
    """校验变量名是否在 config.VARIABLES 中。"""
    invalid = [n for n in names if n not in config.VARIABLES]
    if invalid:
        logger.error(f"未知变量: {', '.join(invalid)}")
        logger.info(f"可用变量: {', '.join(config.VARIABLES.keys())}")
        sys.exit(1)
    return names


def _get_targets(
    var_names: list[str], level_hpa: int | None
) -> list[tuple[str, dict, int | None]]:
    """枚举 (variable_name, var_cfg, hpa) 组合。

    按变量 level_type 分支：
    - isobaric: 按 --level 或全部 8 等压面
    - both: 等压面 + 2m（--level 缺省时同时生成）
    - single: 忽略 --level，走单层
    """
    targets: list[tuple[str, dict, int | None]] = []
    for var_name in var_names:
        var_cfg = config.VARIABLES[var_name]
        lt = var_cfg["level_type"]

        if lt in ("isobaric", "both"):
            if level_hpa is not None:
                if not any(lv["hpa"] == level_hpa for lv in config.PRESSURE_LEVELS):
                    logger.error(f"未知等压面层: {level_hpa} hPa")
                    sys.exit(1)
                targets.append((var_name, var_cfg, level_hpa))
            else:
                for lv in config.PRESSURE_LEVELS:
                    targets.append((var_name, var_cfg, lv["hpa"]))

        if lt == "both" and level_hpa is None:
            # both 变量额外加 2m 单层版本
            targets.append((var_name, var_cfg, None))

        if lt == "single":
            targets.append((var_name, var_cfg, None))

    return targets


# ── 数据获取阶段 ─────────────────────────────────────────────────────
def run_acquisition(
    forecast_hours: int | None = None,
    var_names: list[str] | None = None,
    level_hpa: int | None = None,
) -> list[Path]:
    """执行数据下载 + 合并裁切阶段。"""
    from .data_acquisition import download_gfs_variable, merge_and_crop

    if var_names is None:
        var_names = ["wind"]

    targets = _get_targets(var_names, level_hpa)
    merged_files: list[Path] = []

    for var_name, var_cfg, hpa in targets:
        single_level_key = var_cfg.get("single_level_key")
        level_token = config._level_token(hpa, single_level_key)
        logger.info(f"========== {var_cfg['display_name']} ({level_token}) ==========")

        raw_files = download_gfs_variable(var_cfg, hpa, forecast_hours)
        if not raw_files:
            logger.warning(f"[{var_cfg['display_name']}/{level_token}] 未下载到任何数据。")
            continue

        merged = merge_and_crop(raw_files, var_cfg, hpa)
        merged_files.append(merged)

    return merged_files


# ── 处理阶段 ─────────────────────────────────────────────────────────
def run_processing(
    var_names: list[str] | None = None,
    level_hpa: int | None = None,
) -> list[Path]:
    """执行地图 PNG + 瓦片生成阶段。"""
    from .processor import process_to_textures

    if var_names is None:
        var_names = ["wind"]

    targets = _get_targets(var_names, level_hpa)
    all_outputs: list[Path] = []

    for var_name, var_cfg, hpa in targets:
        single_level_key = var_cfg.get("single_level_key")
        level_token = config._level_token(hpa, single_level_key)
        nc_path = (
            config.processed_data_dir_for(
                var_name, hpa=hpa, single_level_key=single_level_key
            )
            / f"{var_name}_merged.nc"
        )
        if not nc_path.exists():
            logger.warning(
                f"[{var_cfg['display_name']}/{level_token}] 找不到数据文件: {nc_path}"
            )
            continue
        outputs = process_to_textures(nc_path, var_cfg, hpa)
        all_outputs.extend(outputs)

    return all_outputs


def run_full_workflow(
    forecast_hours: int | None = None,
    var_names: list[str] | None = None,
    level_hpa: int | None = None,
) -> None:
    """完整流水线: 下载 → 合并裁切 → 地图可视化。"""
    if var_names is None:
        var_names = ["wind"]

    logger.info("=" * 60)
    logger.info(f"Atmos Toolkit 完整流水线启动（变量: {', '.join(var_names)}）")

    merged_files = run_acquisition(forecast_hours, var_names, level_hpa)
    if not merged_files:
        logger.error("数据获取失败，终止。")
        sys.exit(1)

    run_processing(var_names, level_hpa)
    logger.info("流水线完成。")


# ── 调度模式 ─────────────────────────────────────────────────────────
def _next_gfs_time() -> datetime:
    """计算下一个 GFS 数据可用时间。

    GFS 在 00/06/12/18 UTC 发布，延迟约 GFS_LATENCY_HOURS 后可下载。
    """
    now = datetime.now(timezone.utc)
    latency = config.GFS_LATENCY_HOURS

    for cycle_hour in config.GFS_CYCLE_HOURS:
        available_at = now.replace(
            hour=cycle_hour, minute=0, second=0, microsecond=0
        ) + timedelta(hours=latency)
        if available_at > now:
            return available_at

    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(
        hour=config.GFS_CYCLE_HOURS[0], minute=0, second=0, microsecond=0
    ) + timedelta(hours=latency)


def run_scheduled(
    forecast_hours: int | None = None,
    var_names: list[str] | None = None,
) -> None:
    """按 GFS 数据发布周期智能调度。

    在每个 GFS 周期数据可用后自动运行流水线（00/06/12/18 UTC + 延迟），
    而非固定间隔轮询。默认仅处理 wind 850 hPa，执行前清理超过 2 天的旧数据。
    通过 SCHEDULE_VARIABLES 环境变量可扩展为多变量调度。
    """
    import os
    from .cleanup import cleanup_old_data

    if var_names is None:
        env_vars = os.getenv("SCHEDULE_VARIABLES")
        var_names = env_vars.split(",") if env_vars else ["wind"]

    level_hpa = 850
    logger.info(
        f"GFS 智能调度模式启动，处理变量: {', '.join(var_names)}；"
        f"等压面变量固定 {level_hpa} hPa 层；"
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
            # 清理仅对 wind 等压面生效（cleanup.py Phase 2 才适配多变量）
            if "wind" in var_names:
                cleanup_old_data(level_hpa)
            run_full_workflow(forecast_hours, var_names, level_hpa)
        except Exception as e:
            logger.error(f"流水线异常: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Atmos Toolkit - GFS 多气象变量地图可视化工具",
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
    parser.add_argument(
        "--variable", "-v",
        type=str,
        default=None,
        help=f"变量名（默认 wind）。可选: {', '.join(config.VARIABLES.keys())}",
    )
    parser.add_argument(
        "--variables",
        nargs="+",
        default=None,
        help="多变量批量（覆盖 --variable）。例: --variables wind temp rh",
    )
    parser.add_argument(
        "--all-variables",
        action="store_true",
        help="处理所有变量所有适用层级",
    )

    args = parser.parse_args()
    var_names = _resolve_var_names(args)

    if args.schedule:
        run_scheduled(args.forecast_hours, var_names)
    elif args.acquire_only:
        run_acquisition(args.forecast_hours, var_names, args.level)
    elif args.process_only:
        run_processing(var_names, args.level)
    else:
        run_full_workflow(args.forecast_hours, var_names, args.level)


if __name__ == "__main__":
    main()
