"""GFS 风场数据下载（NOMADS GRIB Filter）。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import xarray as xr

from . import config
from .utils import setup_logger

logger = setup_logger("wind_toolkit.acquisition")


def _build_grib_filter_url(
    date: datetime,
    cycle: int,
    forecast_hour: int,
    grib_level: str,
) -> str:
    """构造 NOMADS GRIB filter 请求 URL。"""
    area = config.DOWNLOAD_AREA
    date_str = date.strftime("%Y%m%d")
    return (
        f"{config.GFS_URL_BASE}?"
        f"file=gfs.t{cycle:02d}z.pgrb2.0p25.f{forecast_hour:03d}"
        f"&{grib_level}=on"
        f"&var_UGRD=on&var_VGRD=on"
        f"&subregion="
        f"&leftlon={int(area['west'])}&rightlon={int(area['east'])}"
        f"&toplat={int(area['north'])}&bottomlat={int(area['south'])}"
        f"&dir=%2Fgfs.{date_str}%2F{cycle:02d}%2Fatmos"
    )


def _check_cycle_available(date: datetime, cycle: int, grib_level: str) -> bool:
    """检查指定 GFS 周期的 f000 数据是否可用。"""
    url = _build_grib_filter_url(date, cycle, 0, grib_level)
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


def _find_latest_cycle(grib_level: str) -> tuple[datetime, int]:
    """查找最新可用的 GFS 预报周期。"""
    now = datetime.now(timezone.utc)
    available_after = now - timedelta(hours=config.GFS_LATENCY_HOURS)

    for offset in range(8):  # 最多回溯 8 个周期（2 天）
        candidate = available_after - timedelta(hours=6 * offset)
        cycle = max(h for h in config.GFS_CYCLE_HOURS if h <= candidate.hour)
        cycle_time = candidate.replace(
            hour=cycle, minute=0, second=0, microsecond=0
        )

        if _check_cycle_available(cycle_time, cycle, grib_level):
            logger.info(
                f"最新 GFS 周期: {cycle_time.strftime('%Y-%m-%d %H:%M')} UTC"
            )
            return cycle_time, cycle

    raise RuntimeError("无法找到可用的 GFS 数据周期，请检查网络连接。")


def _download_forecast_hour(
    date: datetime,
    cycle: int,
    forecast_hour: int,
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

    url = _build_grib_filter_url(date, cycle, forecast_hour, grib_level)
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


def download_gfs_wind(
    level: dict,
    forecast_hours: int | None = None,
) -> list[Path]:
    """下载 GFS 风场数据，返回 GRIB2 文件路径列表。"""
    if forecast_hours is None:
        forecast_hours = config.GFS_FORECAST_HOURS

    grib_level = level["grib_param"]
    level_dir = config.raw_data_dir_for_level(level["hpa"])

    cycle_time, cycle = _find_latest_cycle(grib_level)
    logger.info(
        f"[{level['label']}] 下载 GFS 风场数据: "
        f"{cycle_time.strftime('%Y-%m-%d %H:%M')} UTC, "
        f"预报 0-{forecast_hours} 小时"
    )

    downloaded: list[Path] = []
    for h in range(forecast_hours + 1):
        path = _download_forecast_hour(cycle_time, cycle, h, grib_level, level_dir)
        if path:
            downloaded.append(path)

    logger.info(f"[{level['label']}] 下载完成，共 {len(downloaded)} 个文件")
    return downloaded


def merge_and_crop(files: list[Path], level: dict) -> Path:
    """合并多个 GRIB2 文件并裁切到展示区域，输出为 NetCDF。"""
    if not files:
        raise FileNotFoundError("没有可处理的数据文件。")

    logger.info(f"[{level['label']}] 合并 {len(files)} 个 GRIB2 文件...")

    frames = []
    for f in sorted(files):
        try:
            ds = xr.open_dataset(f, engine="cfgrib")
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

    out_dir = config.processed_data_dir_for_level(level["hpa"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "wind_merged.nc"
    cropped.to_netcdf(out_path)
    logger.info(f"[{level['label']}] 合并裁切完成: {out_path}")

    for ds in frames:
        ds.close()

    return out_path
