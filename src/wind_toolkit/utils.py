"""通用工具函数。"""

import logging
from datetime import datetime, timezone, timedelta


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """创建带格式的 logger。"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter(
            "[%(asctime)s] %(name)s %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


BEIJING_TZ = timezone(timedelta(hours=8))
UTC = timezone.utc


def utc_to_beijing(dt: datetime) -> datetime:
    """UTC 转北京时间。"""
    return dt.astimezone(BEIJING_TZ)


def beijing_to_utc(dt: datetime) -> datetime:
    """北京时间转 UTC。"""
    return dt.astimezone(UTC)


def format_timestamp(dt: datetime) -> str:
    """格式化时间戳为 Unix 秒数字符串，与 manifest 中的时间戳一致。"""
    return str(int(dt.timestamp()))
