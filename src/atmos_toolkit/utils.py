"""通用工具函数。"""

import logging
import time
from datetime import datetime, timezone, timedelta


BEIJING_TZ = timezone(timedelta(hours=8))
UTC = timezone.utc


def _beijing_time_converter(seconds: float) -> time.struct_time:
    """logging 时间戳转北京时间（替换默认的 time.localtime）。"""
    return datetime.fromtimestamp(seconds, tz=UTC).astimezone(BEIJING_TZ).timetuple()


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """创建带格式的 logger（时间戳统一显示北京时间，带日期）。"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter(
            "[%(asctime)s] %(name)s %(levelname)s: %(message)s",
            datefmt="%m-%d %H:%M:%S",
        )
        fmt.converter = _beijing_time_converter
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def utc_to_beijing(dt: datetime) -> datetime:
    """UTC 转北京时间。"""
    return dt.astimezone(BEIJING_TZ)


def beijing_to_utc(dt: datetime) -> datetime:
    """北京时间转 UTC。"""
    return dt.astimezone(UTC)


def format_timestamp(dt: datetime) -> str:
    """格式化时间戳为 Unix 秒数字符串，与 manifest 中的时间戳一致。"""
    return str(int(dt.timestamp()))
