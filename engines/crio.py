"""
CRI-O engine adapter (CRI endpoint provider)

Note:
- Our CRI performance tests are executed via `crictl` in `executor/cri_executor.py`.
- This engine exists mainly to provide a distinct engine name/type and endpoint in config/CLI.
"""

import os
from typing import Dict, Any, Optional, List

from .base import BaseEngine, EngineType, ContainerInfo, ImageInfo
from core.config import EngineConfig


class CRIoEngine(BaseEngine):
    """CRI-O 引擎适配器（主要用于 CRI 场景的端点配置）"""

    def __init__(self, config: EngineConfig):
        super().__init__(config)
        self.endpoint = config.endpoint

    def get_engine_type(self) -> EngineType:
        return EngineType.CRIO

    async def connect(self) -> bool:
        # Best-effort: for unix socket endpoints, just check path exists.
        ep = self.endpoint or ""
        if ep.startswith("unix://"):
            sock = ep.replace("unix://", "", 1)
            self.connected = os.path.exists(sock)
            return self.connected
        self.connected = True
        return True

    async def disconnect(self):
        self.connected = False

    async def is_connected(self) -> bool:
        return self.connected

    # The below operations are not used by our CRI benchmark path (we use `crictl`).
    async def create_container(self, image: str, name: Optional[str] = None,
                               command: Optional[List[str]] = None,
                               ports: Optional[Dict[str, Any]] = None) -> ContainerInfo:
        raise NotImplementedError("CRIoEngine operations are executed via CRIExecutor (crictl)")

    async def start_container(self, container_id: str) -> bool:
        raise NotImplementedError("CRIoEngine operations are executed via CRIExecutor (crictl)")

    async def stop_container(self, container_id: str, timeout: int = 30) -> bool:
        raise NotImplementedError("CRIoEngine operations are executed via CRIExecutor (crictl)")

    async def remove_container(self, container_id: str, force: bool = False) -> bool:
        raise NotImplementedError("CRIoEngine operations are executed via CRIExecutor (crictl)")

    async def pull_image(self, image: str) -> ImageInfo:
        raise NotImplementedError("CRIoEngine operations are executed via CRIExecutor (crictl)")

    async def remove_image(self, image_id: str) -> bool:
        raise NotImplementedError("CRIoEngine operations are executed via CRIExecutor (crictl)")

    async def list_containers(self, all: bool = False) -> List[ContainerInfo]:
        raise NotImplementedError("CRIoEngine operations are executed via CRIExecutor (crictl)")

    async def list_images(self) -> List[ImageInfo]:
        raise NotImplementedError("CRIoEngine operations are executed via CRIExecutor (crictl)")

    async def get_container_stats(self, container_id: str) -> Dict[str, Any]:
        raise NotImplementedError("CRIoEngine operations are executed via CRIExecutor (crictl)")
