"""GFS 气象变量数据下载（NOMADS GRIB Filter）。

支持任意 GFS 变量的下载与合并裁切。通过 `config.VARIABLES` 字典配置每个变量的
GRIB 参数、层级类型、NetCDF 候选变量名等。等压面变量（wind/temp/rh/...）按 hPa
分目录，单层变量（vis/tcdc/pres/...）按虚拟 token（surface/2m/atmos/msl）分目录。
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import xarray as xr

from . import config
from .utils import setup_logger

logger = setup_logger("atmos_toolkit.acquisition")


def _build_grib_filter_url(
    date: datetime,
    cycle: int,
    forecast_hour: int,
    var_names: list[str],
    grib_level: str,
) -> str:
    """构造 NOMADS GRIB filter 请求 URL。

    Args:
        var_names: 要下载的 GFS 变量名列表，如 ["UGRD", "VGRD"] 或 ["TMP"]
        grib_level: NOMADS 层级参数，如 lev_850_mb / lev_surface / lev_entire_atmosphere
    """
    area = config.DOWNLOAD_AREA
    date_str = date.strftime("%Y%m%d")
    var_params = "".join(f"&var_{v}=on" for v in var_names)
    return (
        f"{config.GFS_URL_BASE}?"
        f"file=gfs.t{cycle:02d}z.pgrb2.0p25.f{forecast_hour:03d}"
        f"&{grib_level}=on"
        f"{var_params}"
        f"&subregion="
        f"&leftlon={int(area['west'])}&rightlon={int(area['east'])}"
        f"&toplat={int(area['north'])}&bottomlat={int(area['south'])}"
        f"&dir=%2Fgfs.{date_str}%2F{cycle:02d}%2Fatmos"
    )


def _check_cycle_available(
    date: datetime, cycle: int, grib_level: str | None = None, probe_var: str = "UGRD"
) -> bool:
    """检查指定 GFS 周期的 f000 数据是否可用。

    周期可用性与具体变量无关，固定用 UGRD + lev_850_mb 探测最稳定。
    grib_level/probe_var 保留为兼容参数，实际探测始终用 wind/850hPa。
    """
    url = _build_grib_filter_url(date, cycle, 0, ["UGRD"], "lev_850_mb")
    try:
        resp = requests.get(url, timeout=30, stream=True)
        if resp.status_code == 200:
            chunk = next(resp.iter_content(chunk_size=4), b"")
            resp.close()
            return chunk[:4] == b"GRIB"
        resp.close()
    except requests.RequestException:
        pass
    return False


def _find_latest_cycle(
    grib_level: str | None = None, probe_var: str = "UGRD"
) -> tuple[datetime, int]:
    """查找最新可用的 GFS 预报周期。周期检测与具体变量解耦。"""
    now = datetime.now(timezone.utc)
    available_after = now - timedelta(hours=config.GFS_LATENCY_HOURS)

    for offset in range(8):  # 最多回溯 8 个周期（2 天）
        candidate = available_after - timedelta(hours=6 * offset)
        cycle = max(h for h in config.GFS_CYCLE_HOURS if h <= candidate.hour)
        cycle_time = candidate.replace(
            hour=cycle, minute=0, second=0, microsecond=0
        )

        if _check_cycle_available(cycle_time, cycle):
            logger.info(
                f"最新 GFS 周期: {cycle_time.strftime('%Y-%m-%d %H:%M')} UTC"
            )
            return cycle_time, cycle

    raise RuntimeError("无法找到可用的 GFS 数据周期，请检查网络连接。")


def _download_forecast_hour(
    date: datetime,
    cycle: int,
    forecast_hour: int,
    var_names: list[str],
    grib_level: str,
    level_dir: Path,
) -> Path | None:
    """下载单个预报时刻的 GRIB2 子集，返回文件路径或 None。"""
    level_dir.mkdir(parents=True, exist_ok=True)
    out_path = (
        level_dir
        / f"gfs_{date.strftime('%Y%m%d')}_{cycle:02d}z_f{forecast_hour:03d}.grib2"
    )

    if out_path.exists() and out_path.stat().st_size > 100:
        logger.info(f"已存在，跳过: {out_path.name}")
        return out_path

    url = _build_grib_filter_url(date, cycle, forecast_hour, var_names, grib_level)
    logger.info(f"下载: f{forecast_hour:03d}")

    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()

        if resp.content[:4] != b"GRIB":
            logger.warning(f"无效的 GRIB2 响应: f{forecast_hour:03d}")
            return None

        out_path.write_bytes(resp.content)
        return out_path
    except requests.RequestException as e:
        logger.warning(f"下载失败 f{forecast_hour:03d}: {e}")
        return None


def _resolve_var_name(var_cfg: dict) -> str:
    """反查 var_cfg 在 config.VARIABLES 中的 key。"""
    return next(k for k, v in config.VARIABLES.items() if v is var_cfg)


def download_gfs_variable(
    var_cfg: dict,
    hpa: int | None,
    forecast_hours: int | None = None,
) -> list[Path]:
    """下载任意 GFS 变量数据，返回 GRIB2 文件路径列表。

    Args:
        var_cfg: 来自 config.VARIABLES 的变量配置字典
        hpa: 等压面 hPa；单层变量传 None
        forecast_hours: 预报时长，None 用 config.GFS_FORECAST_HOURS
    """
    if forecast_hours is None:
        forecast_hours = config.GFS_FORECAST_HOURS

    var_names = var_cfg["grib_vars"]
    grib_level = config.level_grib_param(var_cfg, hpa)
    var_name = _resolve_var_name(var_cfg)
    single_level_key = var_cfg.get("single_level_key")
    level_dir = config.raw_data_dir_for(var_name, hpa=hpa, single_level_key=single_level_key)
    level_token = config._level_token(hpa, single_level_key)

    probe = var_names[0]
    cycle_time, cycle = _find_latest_cycle()
    logger.info(
        f"[{var_cfg['display_name']}/{level_token}] 下载 GFS 数据: "
        f"{cycle_time.strftime('%Y-%m-%d %H:%M')} UTC, "
        f"预报 0-{forecast_hours} 小时"
    )

    downloaded: list[Path] = []
    for h in range(forecast_hours + 1):
        path = _download_forecast_hour(
            cycle_time, cycle, h, var_names, grib_level, level_dir
        )
        if path:
            downloaded.append(path)

    logger.info(
        f"[{var_cfg['display_name']}/{level_token}] 下载完成，共 {len(downloaded)} 个文件"
    )
    return downloaded


def download_gfs_wind(
    level: dict, forecast_hours: int | None = None
) -> list[Path]:
    """向后兼容包装：下载风场数据。"""
    return download_gfs_variable(
        config.VARIABLES["wind"], level["hpa"], forecast_hours
    )


def _open_grib_dataset(path: Path, step_type: str | None):
    """打开 GRIB2 文件，遇到 stepType 冲突时自动用 filter_by_keys 回退。"""
    try:
        return xr.open_dataset(path, engine="cfgrib")
    except Exception as e:
        msg = str(e)
        if "filter_by_keys" not in msg:
            raise
        # cfgrib 报 multiple values for unique key，按变量配置选择 stepType
        keys = {"stepType": step_type} if step_type else {"stepType": "instant"}
        return xr.open_dataset(path, engine="cfgrib", filter_by_keys=keys)


def merge_and_crop(
    files: list[Path], var_cfg: dict, hpa: int | None = None
) -> Path:
    """合并多个 GRIB2 文件并裁切到展示区域，输出为 NetCDF。"""
    if not files:
        raise FileNotFoundError("没有可处理的数据文件。")

    var_name = _resolve_var_name(var_cfg)
    single_level_key = var_cfg.get("single_level_key")
    level_token = config._level_token(hpa, single_level_key)

    logger.info(
        f"[{var_cfg['display_name']}/{level_token}] 合并 {len(files)} 个 GRIB2 文件..."
    )

    frames = []
    step_type = var_cfg.get("step_type")
    for f in sorted(files):
        try:
            ds = _open_grib_dataset(f, step_type)
            # cfgrib 用 time 表示分析时间（所有文件相同），valid_time 才是有效时间
            vt = ds.valid_time.values
            ds = ds.drop_vars(
                ["time", "step", "valid_time", "isobaricInhPa"],
                errors="ignore",
            )
            ds = ds.expand_dims(time=[vt])
            frames.append(ds)
        except Exception as e:
            logger.warning(f"无法读取 {f.name}: {e}")

    if not frames:
        raise RuntimeError("所有文件读取失败。")

    merged = (
        xr.concat(frames, dim="time", coords="minimal")
        if len(frames) > 1
        else frames[0]
    )

    # 裁切到展示区域（注意纬度方向）
    lat_name = "latitude" if "latitude" in merged.dims else "lat"
    lon_name = "longitude" if "longitude" in merged.dims else "lon"

    # GFS 经度可能是 0–360 范围，归一化到 -180–180 以匹配展示区域
    lon_vals = merged[lon_name].values
    if float(lon_vals.max()) > 180:
        merged = merged.assign_coords(
            {lon_name: (((merged[lon_name] + 180) % 360) - 180)}
        ).sortby(lon_name)

    lat_vals = merged[lat_name].values

    display = config.DISPLAY_AREA
    if lat_vals[0] < lat_vals[-1]:
        # 纬度升序
        lat_slice = slice(display["south"], display["north"])
    else:
        # 纬度降序
        lat_slice = slice(display["north"], display["south"])

    cropped = merged.sel(
        {
            lat_name: lat_slice,
            lon_name: slice(display["west"], display["east"]),
        }
    )

    out_dir = config.processed_data_dir_for(
        var_name, hpa=hpa, single_level_key=single_level_key
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{var_name}_merged.nc"
    cropped.to_netcdf(out_path)
    logger.info(
        f"[{var_cfg['display_name']}/{level_token}] 合并裁切完成: {out_path}"
    )

    for ds in frames:
        ds.close()

    return out_path
