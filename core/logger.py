"""
Logging configuration for iSulad Performance Testing Framework
"""

import sys
import logging
from pathlib import Path
from typing import Optional
from loguru import logger


def setup_logging(config: Optional[dict] = None):
    """设置日志配置"""
    if config is None:
        config = {
            "level": "INFO",
            "file": "isulad-perf.log",
            "max_size": "10MB",
            "backup_count": 5
        }

    # 移除默认处理器
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stdout,
        level=config.get("level", "INFO"),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True
    )

    # 文件输出
    log_file = config.get("file", "isulad-perf.log")
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file,
            level=config.get("level", "INFO"),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation=config.get("max_size", "10MB"),
            retention=config.get("backup_count", 5),
            encoding="utf-8"
        )


def get_logger(name: str = "isulad-perf"):
    """获取日志器"""
    return logger.bind(name=name)
