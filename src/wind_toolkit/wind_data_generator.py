"""风力粒子流数据生成模块。

从 NetCDF U/V 风场分量生成 wind-layer 兼容的 JSON 数据，
供 Mapbox/MapLibre 前端渲染动态风力粒子效果。
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np

from . import config
from .utils import setup_logger

logger = setup_logger("atmos_toolkit.particle")


def generate_wind_particle_data(
    u: np.ndarray,
    v: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    timestamp: str,
    level_hpa: int,
    ref_time: datetime,
    output_dir: Path | None = None,
) -> Path:
    """生成 wind-layer jsonArray 格式的粒子风场 JSON。

    Args:
        u: 2D U 分量 (lat × lon)
        v: 2D V 分量 (lat × lon)
        lat: 1D 纬度数组
        lon: 1D 经度数组
        timestamp: Unix 时间戳字符串（作为文件名）
        level_hpa: 等压面 hPa 值
        ref_time: 参考时间
        output_dir: 输出目录

    Returns:
        生成的 JSON 文件路径
    """
    if output_dir is None:
        output_dir = config.particle_data_dir_for_level(level_hpa)
    output_dir.mkdir(parents=True, exist_ok=True)

    ny, nx = u.shape
    dx = round(float(lon[1] - lon[0]), 4) if len(lon) > 1 else 0.25
    dy = round(float(lat[1] - lat[0]), 4) if len(lat) > 1 else 0.25

    # wind-layer 期望 la1 >= la2（北到南扫描），如果纬度递增则翻转
    if lat[0] < lat[-1]:
        u = u[::-1]
        v = v[::-1]
        la1, la2 = float(lat[-1]), float(lat[0])
    else:
        la1, la2 = float(lat[0]), float(lat[-1])

    lo1, lo2 = float(lon[0]), float(lon[-1])
    ref_time_str = ref_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    result = [
        _build_component(u, nx, ny, dx, dy, la1, la2, lo1, lo2, ref_time_str, 2, 2),
        _build_component(v, nx, ny, dx, dy, la1, la2, lo1, lo2, ref_time_str, 2, 3),
    ]

    out_path = output_dir / f"{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    logger.info(f"粒子数据已生成: {out_path.name} ({out_path.stat().st_size / 1024:.0f} KB)")
    return out_path


def _build_component(
    data: np.ndarray,
    nx: int,
    ny: int,
    dx: float,
    dy: float,
    la1: float,
    la2: float,
    lo1: float,
    lo2: float,
    ref_time: str,
    param_cat: int,
    param_num: int,
) -> dict:
    """构建单个风场分量的 jsonArray 元素。"""
    flat = data.flatten().tolist()
    # NaN → None（JSON null），wind-layer 跳过 null 值
    flat = [None if isinstance(v, float) and (v != v) else round(v, 4) for v in flat]

    return {
        "header": {
            "parameterCategory": param_cat,
            "parameterNumber": param_num,
            "dx": dx,
            "dy": dy,
            "la1": la1,
            "la2": la2,
            "lo1": lo1,
            "lo2": lo2,
            "nx": nx,
            "ny": ny,
            "refTime": ref_time,
        },
        "data": flat,
    }
