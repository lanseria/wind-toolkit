"""将 NetCDF 数据处理为地图可视化 PNG 与 XYZ 瓦片。

通用入口 `process_to_textures` 支持任意气象变量：
- vector（风场）：调用 generate_wind_map + generate_wind_tiles + 风场粒子数据
- scalar（温度/湿度/云量/降水/能见度/气压/HGT/GUST 等）：单位转换 + generate_scalar_map + generate_scalar_tiles
"""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from . import config
from .map_visualizer import generate_scalar_map, generate_wind_map
from .tile_generator import (
    generate_scalar_tiles,
    generate_wind_tiles,
    update_tiles_manifest,
)
from .utils import format_timestamp, setup_logger
from .wind_data_generator import generate_wind_particle_data

logger = setup_logger("atmos_toolkit.processor")


def _identify_nc_var(ds: xr.Dataset, var_cfg: dict) -> str | tuple[str, str]:
    """根据 var_cfg['nc_names'] 候选列表识别 NetCDF 中的变量名。

    Returns:
        vector 变量: (u_name, v_name)
        scalar 变量: name
    """
    actual = [str(v) for v in ds.data_vars]
    candidates = var_cfg["nc_names"]

    if var_cfg["kind"] == "vector":
        u_cands = [c.lower() for c in candidates[0]]
        v_cands = [c.lower() for c in candidates[1]]
        u_name = next(
            (v for v in actual if v.lower() in u_cands),
            actual[0] if actual else None,
        )
        v_name = next(
            (v for v in actual if v.lower() in v_cands),
            actual[1] if len(actual) > 1 else actual[0],
        )
        if u_name is None or v_name is None:
            raise ValueError(f"NetCDF 中找不到 vector 变量候选: {actual}")
        return u_name, v_name

    cands = [c.lower() for c in candidates[0]]
    name = next((v for v in actual if v.lower() in cands), None)
    if name is None:
        logger.warning(
            f"未匹配到变量候选 {candidates[0]}，回退到首个 data_var: {actual[0] if actual else None}"
        )
        name = actual[0]
    return name


def _resolve_var_name(var_cfg: dict) -> str:
    """反查 var_cfg 在 config.VARIABLES 中的 key。"""
    return next(k for k, v in config.VARIABLES.items() if v is var_cfg)


def _build_level_label(var_cfg: dict, hpa: int | None) -> str:
    """构造层级标签（用于标题和日志）。"""
    if hpa is not None:
        lv = next(l for l in config.PRESSURE_LEVELS if l["hpa"] == hpa)
        return f"{lv['label']} ({lv['height']})"
    sk = var_cfg.get("single_level_key")
    return config.SINGLE_LEVEL_KEYS.get(sk, sk or "")


def process_to_textures(
    nc_path: Path, var_cfg: dict, hpa: int | None = None
) -> list[Path]:
    """将合并后的 NetCDF 处理为地图 PNG + XYZ 瓦片（+ 风场粒子数据）。

    Args:
        nc_path: 合并裁切后的 NetCDF 文件路径
        var_cfg: 来自 config.VARIABLES 的变量配置
        hpa: 等压面 hPa；单层变量传 None

    Returns:
        生成的 PNG 文件路径列表
    """
    var_name = _resolve_var_name(var_cfg)
    single_level_key = var_cfg.get("single_level_key")
    level_label = _build_level_label(var_cfg, hpa)
    log_prefix = f"{var_cfg['display_name']}/{level_label}"

    ds = xr.open_dataset(nc_path)
    logger.info(
        f"[{log_prefix}] 加载 NetCDF: dims={dict(ds.dims)}, "
        f"时间范围 {ds.time.values[0]} ~ {ds.time.values[-1]}"
    )

    lat_name = "latitude" if "latitude" in ds.dims else "lat"
    lon_name = "longitude" if "longitude" in ds.dims else "lon"
    lat_vals = ds[lat_name].values
    lon_vals = ds[lon_name].values

    times = ds.time.values
    output_files: list[Path] = []
    datetimes: list[datetime] = []

    textures_dir = config.textures_dir_for(
        var_name, hpa=hpa, single_level_key=single_level_key
    )
    textures_dir.mkdir(parents=True, exist_ok=True)
    tile_dir = config.tile_dir_for(
        var_name, hpa=hpa, single_level_key=single_level_key
    )
    tile_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = config.tile_manifest_for(
        var_name, hpa=hpa, single_level_key=single_level_key
    )

    for i, t_np in enumerate(times):
        t = _to_datetime(t_np)
        stamp = format_timestamp(t)
        datetimes.append(t)

        out_path = textures_dir / f"{stamp}.png"

        if var_cfg["kind"] == "vector":
            u_name, v_name = _identify_nc_var(ds, var_cfg)
            u_data = ds[u_name].isel(time=i).values
            v_data = ds[v_name].isel(time=i).values

            generate_wind_map(u_data, v_data, lat_vals, lon_vals, t, out_path, level_label)
            generate_wind_tiles(
                u_data, v_data, lat_vals, lon_vals, stamp, output_dir=tile_dir
            )

            if var_cfg.get("generate_particle"):
                particle_dir = config.particle_data_dir_for(
                    var_name, hpa=hpa, single_level_key=single_level_key
                )
                generate_wind_particle_data(
                    u_data, v_data, lat_vals, lon_vals, stamp,
                    level_hpa=hpa or 850, ref_time=t,
                    output_dir=particle_dir,
                )
        else:
            name = _identify_nc_var(ds, var_cfg)
            raw = ds[name].isel(time=i).values
            data = config.apply_unit_convert(raw, var_cfg)

            generate_scalar_map(
                data, lat_vals, lon_vals, t, out_path, var_cfg, level_label
            )
            generate_scalar_tiles(
                data, lat_vals, lon_vals, stamp, var_cfg, output_dir=tile_dir
            )

        output_files.append(out_path)
        if (i + 1) % 5 == 0 or i == len(times) - 1:
            logger.info(f"  [{log_prefix}] 进度: {i + 1}/{len(times)} 帧")

    ds.close()
    particle_dir = config.particle_data_dir_for(
        var_name, hpa=hpa, single_level_key=single_level_key
    )
    update_tiles_manifest(datetimes, manifest_path, particle_dir=particle_dir)
    logger.info(f"[{log_prefix}] 地图生成完成: {len(output_files)} 张 → {textures_dir}")
    return output_files


def _to_datetime(t_np) -> datetime:
    """将 numpy datetime64 转为 Python datetime (UTC)。"""
    ts = (t_np - np.datetime64("1970-01-01T00:00:00")) / np.timedelta64(1, "s")
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)
