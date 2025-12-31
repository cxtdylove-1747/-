"""
Base result reporter interface
"""

import abc
import os
from typing import Dict, Any, Optional
from enum import Enum
from pathlib import Path

from processor.base import ProcessedData


class ReporterType(Enum):
    """展示器类型枚举"""
    CONSOLE = "console"
    HTML = "html"
    JSON = "json"
    CSV = "csv"


class BaseReporter(abc.ABC):
    """结果展示器基础接口"""

    def __init__(self, output_dir: str = "./results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @abc.abstractmethod
    def report(self, processed_data: ProcessedData, output_file: Optional[str] = None) -> str:
        """生成报告"""
        pass

    @abc.abstractmethod
    def get_reporter_type(self) -> ReporterType:
        """获取展示器类型"""
        pass

    def _ensure_output_dir(self):
        """确保输出目录存在"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_output_path(self, filename: str) -> Path:
        """获取输出文件路径"""
        return self.output_dir / filename

    def _format_duration(self, duration: float) -> str:
        """格式化持续时间"""
        if duration < 1e-6:
            return f"{duration * 1e9:.2f} ns"
        if duration < 1e-3:
            return f"{duration * 1e6:.2f} µs"
        if duration < 1:
            return f"{duration * 1e3:.3f} ms"
        if duration < 60:
            return f"{duration:.3f} s"
        minutes = int(duration // 60)
        seconds = duration % 60
        return f"{minutes}m{seconds:.1f}s"

    def _format_percentage(self, value: float) -> str:
        """格式化百分比"""
        return f"{value * 100:.1f}%"

    def _format_number(self, value: float, precision: int = 2) -> str:
        """格式化数字"""
        return f"{value:.{precision}f}"
