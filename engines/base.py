"""
Base engine interface for container engines
"""

import abc
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass

from core.config import EngineConfig
from core.exceptions import EngineError, ConnectionError


class EngineType(Enum):
    """引擎类型枚举"""
    ISULAD = "isulad"
    DOCKER = "docker"
    CRIO = "crio"
    CONTAINERD = "containerd"


@dataclass
class ContainerInfo:
    """容器信息"""
    id: str
    name: str
    image: str
    status: str
    created_at: float
    ports: Optional[Dict[str, Any]] = None
    labels: Optional[Dict[str, str]] = None


@dataclass
class ImageInfo:
    """镜像信息"""
    id: str
    name: str
    tag: str
    size: int
    created_at: float


@dataclass
class PerformanceMetrics:
    """性能指标"""
    operation: str
    start_time: float
    end_time: float
    duration: float
    success: bool
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    warmup: bool = False


class BaseEngine(abc.ABC):
    """容器引擎基础接口"""

    def __init__(self, config: EngineConfig):
        self.config = config
        self.connected = False
        self._client = None

    @abc.abstractmethod
    async def connect(self) -> bool:
        """连接到容器引擎"""
        pass

    @abc.abstractmethod
    async def disconnect(self):
        """断开连接"""
        pass

    @abc.abstractmethod
    async def is_connected(self) -> bool:
        """检查连接状态"""
        pass

    @abc.abstractmethod
    async def create_container(self, image: str, name: Optional[str] = None,
                              command: Optional[List[str]] = None,
                              ports: Optional[Dict[str, Any]] = None) -> ContainerInfo:
        """创建容器"""
        pass

    @abc.abstractmethod
    async def start_container(self, container_id: str) -> bool:
        """启动容器"""
        pass

    @abc.abstractmethod
    async def stop_container(self, container_id: str, timeout: int = 30) -> bool:
        """停止容器"""
        pass

    @abc.abstractmethod
    async def remove_container(self, container_id: str, force: bool = False) -> bool:
        """删除容器"""
        pass

    @abc.abstractmethod
    async def pull_image(self, image: str) -> ImageInfo:
        """拉取镜像"""
        pass

    @abc.abstractmethod
    async def remove_image(self, image_id: str) -> bool:
        """删除镜像"""
        pass

    @abc.abstractmethod
    async def list_containers(self, all: bool = False) -> List[ContainerInfo]:
        """列出容器"""
        pass

    @abc.abstractmethod
    async def list_images(self) -> List[ImageInfo]:
        """列出镜像"""
        pass

    @abc.abstractmethod
    async def get_container_stats(self, container_id: str) -> Dict[str, Any]:
        """获取容器统计信息"""
        pass

    @abc.abstractmethod
    def get_engine_type(self) -> EngineType:
        """获取引擎类型"""
        pass

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            return await self.is_connected()
        except Exception:
            return False

    async def cleanup(self):
        """清理资源"""
        try:
            await self.disconnect()
        except Exception:
            pass

    def _create_performance_metrics(self, operation: str, start_time: float,
                                   end_time: float, success: bool,
                                   error_message: Optional[str] = None,
                                   metadata: Optional[Dict[str, Any]] = None) -> PerformanceMetrics:
        """创建性能指标对象"""
        return PerformanceMetrics(
            operation=operation,
            start_time=start_time,
            end_time=end_time,
            duration=end_time - start_time,
            success=success,
            error_message=error_message,
            metadata=metadata or {}
        )
