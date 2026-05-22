"""过期数据清理模块。

在每次定时任务执行前清理超过指定天数的数据：
- 瓦片 PNG、纹理 PNG、粒子 JSON、原始数据、处理后数据
- 更新 tiles_manifest.json 移除过期时间戳
"""

import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

from . import config
from .utils import setup_logger

logger = setup_logger("wind_toolkit.cleanup")

DEFAULT_MAX_AGE_DAYS = 2


def cleanup_old_data(level_hpa: int, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> None:
    """清理指定等压面层中超过 max_age_days 天的所有数据。"""
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=max_age_days)).timestamp())
    level_label = f"{level_hpa}hPa"
    logger.info(f"开始清理 {level_label} 中超过 {max_age_days} 天的数据（截止时间戳: {cutoff}）")

    # 瓦片 PNG: wind-tiles/{level}/{z}/{x}/{y}/{timestamp}.png
    tile_dir = config.tile_dir_for_level(level_hpa)
    tile_count = _cleanup_timestamped_files(tile_dir, ".png", cutoff, recursive=True)

    # 粒子 JSON: wind-tiles/{level}/particle/{timestamp}.json
    particle_dir = config.particle_data_dir_for_level(level_hpa)
    particle_count = _cleanup_timestamped_files(particle_dir, ".json", cutoff)

    # 纹理 PNG: outputs/textures/{level}/{timestamp}.png
    textures_dir = config.textures_dir_for_level(level_hpa)
    texture_count = _cleanup_timestamped_files(textures_dir, ".png", cutoff)

    # 原始数据: data/raw/{level}/
    raw_dir = config.raw_data_dir_for_level(level_hpa)
    raw_count = _cleanup_directory_contents(raw_dir, cutoff)

    # 处理后数据: data/processed/{level}/
    processed_dir = config.processed_data_dir_for_level(level_hpa)
    processed_count = _cleanup_directory_contents(processed_dir, cutoff)

    # 更新 manifest
    manifest_count = _cleanup_manifest(level_hpa, cutoff)

    # 清理空目录
    _cleanup_empty_dirs(tile_dir)
    _cleanup_empty_dirs(textures_dir)

    total = tile_count + particle_count + texture_count + raw_count + processed_count
    logger.info(
        f"清理完成: 瓦片 {tile_count}, 粒子 {particle_count}, "
        f"纹理 {texture_count}, 原始数据 {raw_count}, "
        f"处理后数据 {processed_count}, manifest 时间戳 {manifest_count}"
    )


def _parse_timestamp(filename: str, suffix: str) -> int | None:
    """从文件名解析 Unix 时间戳。"""
    name = filename.removesuffix(suffix)
    try:
        ts = int(name)
        if ts > 1_000_000_000:  # 合理的 Unix 时间戳范围
            return ts
    except ValueError:
        pass
    return None


def _cleanup_timestamped_files(
    directory: Path, suffix: str, cutoff: int, *, recursive: bool = False
) -> int:
    """清理目录中文件名含过期时间戳的文件。"""
    if not directory.exists():
        return 0

    pattern = "**/*" + suffix if recursive else "*" + suffix
    count = 0
    for f in directory.glob(pattern):
        if not f.is_file():
            continue
        ts = _parse_timestamp(f.name, suffix)
        if ts is not None and ts < cutoff:
            f.unlink()
            count += 1

    if count > 0:
        logger.info(f"  {directory.name}: 删除 {count} 个过期 {suffix} 文件")
    return count


def _cleanup_directory_contents(directory: Path, cutoff: int) -> int:
    """清理目录中的所有文件（按文件修改时间判断过期）。"""
    if not directory.exists():
        return 0

    cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
    count = 0
    for f in directory.iterdir():
        if f.is_file():
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff_dt:
                f.unlink()
                count += 1
        elif f.is_dir():
            # 子目录按目录修改时间判断
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff_dt:
                shutil.rmtree(f)
                count += 1

    if count > 0:
        logger.info(f"  {directory.name}: 删除 {count} 个过期文件/目录")
    return count


def _cleanup_manifest(level_hpa: int, cutoff: int) -> int:
    """从 tiles_manifest.json 中移除过期时间戳。"""
    manifest_path = config.tile_manifest_for_level(level_hpa)
    if not manifest_path.exists():
        return 0

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    old_count = len(manifest.get("timestamps", []))
    manifest["timestamps"] = [ts for ts in manifest.get("timestamps", []) if ts >= cutoff]
    removed = old_count - len(manifest["timestamps"])

    # 同步清理 particle filenames
    if "particle" in manifest:
        old_particle = manifest["particle"].get("filenames", [])
        new_particle = [
            fn for fn in old_particle
            if _parse_timestamp(fn, ".json") is not None
            and _parse_timestamp(fn, ".json") >= cutoff
        ]
        manifest["particle"]["filenames"] = new_particle
        manifest["particle"]["available"] = len(new_particle) > 0

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    if removed > 0:
        logger.info(f"  manifest: 移除 {removed} 个过期时间戳")
    return removed


def _cleanup_empty_dirs(directory: Path) -> None:
    """递归清理空目录（保留指定层级以上的目录）。"""
    if not directory.exists():
        return
    for dirpath in sorted(directory.rglob("*"), reverse=True):
        if dirpath.is_dir() and not any(dirpath.iterdir()):
            dirpath.rmdir()
