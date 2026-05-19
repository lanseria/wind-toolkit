"""将风场数据处理为地图可视化 PNG。"""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from . import config
from .map_visualizer import generate_wind_map
from .tile_generator import generate_wind_tiles, update_tiles_manifest
from .utils import format_timestamp, setup_logger

logger = setup_logger("wind_toolkit.processor")


def process_to_textures(nc_path: Path) -> list[Path]:
    """将合并后的 NetCDF 处理为风场地图可视化 PNG。

    Args:
        nc_path: 合并裁切后的 NetCDF 文件路径

    Returns:
        生成的 PNG 文件路径列表
    """
    ds = xr.open_dataset(nc_path)
    logger.info(f"加载 NetCDF: {ds.dims}, 时间范围 {ds.time.values[0]} ~ {ds.time.values[-1]}")

    # 识别变量名
    var_names = list(ds.data_vars)
    u_var = next(
        (v for v in var_names if v.lower() in ("u10", "ugrd", "10m_u_component_of_wind")),
        var_names[0],
    )
    v_var = next(
        (v for v in var_names if v.lower() in ("v10", "vgrd", "10m_v_component_of_wind")),
        var_names[1] if len(var_names) > 1 else var_names[0],
    )

    lat_name = "latitude" if "latitude" in ds.dims else "lat"
    lon_name = "longitude" if "longitude" in ds.dims else "lon"
    lat_vals = ds[lat_name].values
    lon_vals = ds[lon_name].values

    times = ds.time.values
    output_files: list[Path] = []
    datetimes: list[datetime] = []

    for i, t_np in enumerate(times):
        t = _to_datetime(t_np)
        stamp = format_timestamp(t)
        datetimes.append(t)

        u_data = ds[u_var].isel(time=i).values
        v_data = ds[v_var].isel(time=i).values

        out_path = config.TEXTURES_DIR / f"{stamp}.png"
        generate_wind_map(u_data, v_data, lat_vals, lon_vals, t, out_path)

        generate_wind_tiles(u_data, v_data, lat_vals, lon_vals, stamp)

        output_files.append(out_path)
        if (i + 1) % 5 == 0 or i == len(times) - 1:
            logger.info(f"  进度: {i + 1}/{len(times)} 帧")

    ds.close()
    update_tiles_manifest(datetimes)
    logger.info(f"地图生成完成: {len(output_files)} 张 → {config.TEXTURES_DIR}")
    return output_files


def _to_datetime(t_np) -> datetime:
    """将 numpy datetime64 转为 Python datetime (UTC)。"""
    ts = (t_np - np.datetime64("1970-01-01T00:00:00")) / np.timedelta64(1, "s")
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)
