"""
Base data processor interface
"""

import abc
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

from executor.base import TestResult


class ProcessorType(Enum):
    """处理器类型枚举"""
    ANALYZER = "analyzer"
    STATISTICS = "statistics"
    COMPARATOR = "comparator"


@dataclass
class ProcessedData:
    """处理后的数据"""
    processor_type: ProcessorType
    test_results: List[TestResult]
    processed_data: Dict[str, Any]
    metadata: Dict[str, Any]
    timestamp: float


class BaseProcessor(abc.ABC):
    """数据处理器基础接口"""

    def __init__(self):
        self.metadata = {}

    @abc.abstractmethod
    def process(self, test_results: List[TestResult]) -> ProcessedData:
        """处理测试结果"""
        pass

    @abc.abstractmethod
    def get_processor_type(self) -> ProcessorType:
        """获取处理器类型"""
        pass

    def set_metadata(self, key: str, value: Any):
        """设置元数据"""
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """获取元数据"""
        return self.metadata.get(key, default)

    def validate_input(self, test_results: List[TestResult]) -> bool:
        """验证输入数据"""
        if not test_results:
            return False

        for result in test_results:
            if not hasattr(result, 'test_name') or not hasattr(result, 'metrics'):
                return False

        return True
