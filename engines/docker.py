"""
Docker container engine adapter
"""

import asyncio
import time
from typing import Dict, Any, Optional, List
import docker

from .base import BaseEngine, EngineType, ContainerInfo, ImageInfo
from core.config import EngineConfig
from core.exceptions import EngineError, ConnectionError


class DockerEngine(BaseEngine):
    """Docker容器引擎适配器"""

    def __init__(self, config: EngineConfig):
        super().__init__(config)
        self.endpoint = config.endpoint
        self.timeout = config.timeout
        self.client = None

    def get_engine_type(self) -> EngineType:
        return EngineType.DOCKER

    async def connect(self) -> bool:
        """连接到Docker"""
        try:
            if self.endpoint.startswith("unix://"):
                socket_path = self.endpoint.replace("unix://", "")
                self.client = docker.APIClient(base_url=f"unix://{socket_path}")
            else:
                # TCP连接
                self.client = docker.APIClient(base_url=self.endpoint)

            # 测试连接
            self.client.ping()
            self.connected = True
            return True

        except Exception as e:
            self.connected = False
            raise ConnectionError(f"Failed to connect to Docker: {e}")

    async def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.close()
            self.client = None
        self.connected = False

    async def is_connected(self) -> bool:
        """检查连接状态"""
        if not self.connected or not self.client:
            return False

        try:
            self.client.ping()
            return True
        except Exception:
            self.connected = False
            return False

    async def create_container(self, image: str, name: Optional[str] = None,
                              command: Optional[List[str]] = None,
                              ports: Optional[Dict[str, Any]] = None) -> ContainerInfo:
        """创建容器"""
        start_time = time.time()
        try:
            container = self.client.create_container(
                image=image,
                name=name,
                command=command,
                ports=ports,
                detach=True
            )

            end_time = time.time()

            return ContainerInfo(
                id=container['Id'],
                name=name or container['Id'][:12],
                image=image,
                status="created",
                created_at=start_time,
                ports=ports
            )

        except Exception as e:
            raise EngineError(f"Failed to create container: {e}")

    async def start_container(self, container_id: str) -> bool:
        """启动容器"""
        start_time = time.time()
        try:
            self.client.start(container_id)
            end_time = time.time()
            return True
        except Exception as e:
            raise EngineError(f"Failed to start container {container_id}: {e}")

    async def stop_container(self, container_id: str, timeout: int = 30) -> bool:
        """停止容器"""
        start_time = time.time()
        try:
            self.client.stop(container_id, timeout=timeout)
            end_time = time.time()
            return True
        except Exception as e:
            raise EngineError(f"Failed to stop container {container_id}: {e}")

    async def remove_container(self, container_id: str, force: bool = False) -> bool:
        """删除容器"""
        start_time = time.time()
        try:
            self.client.remove_container(container_id, force=force)
            end_time = time.time()
            return True
        except Exception as e:
            raise EngineError(f"Failed to remove container {container_id}: {e}")

    async def pull_image(self, image: str) -> ImageInfo:
        """拉取镜像"""
        start_time = time.time()
        try:
            # Docker Python库的pull是同步的，需要在executor中运行
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.client.pull, image)

            # 获取镜像信息
            images = self.client.images(name=image)
            if images:
                image_info = images[0]
                name, tag = image.split(":") if ":" in image else (image, "latest")

                end_time = time.time()

                return ImageInfo(
                    id=image_info['Id'],
                    name=name,
                    tag=tag,
                    size=image_info.get('Size', 0),
                    created_at=start_time
                )
            else:
                raise EngineError(f"Failed to get image info after pull: {image}")

        except Exception as e:
            raise EngineError(f"Failed to pull image {image}: {e}")

    async def remove_image(self, image_id: str) -> bool:
        """删除镜像"""
        try:
            self.client.remove_image(image_id)
            return True
        except Exception as e:
            raise EngineError(f"Failed to remove image {image_id}: {e}")

    async def list_containers(self, all: bool = False) -> List[ContainerInfo]:
        """列出容器"""
        try:
            containers = self.client.containers(all=all)

            result = []
            for container in containers:
                result.append(ContainerInfo(
                    id=container['Id'],
                    name=container['Names'][0] if container['Names'] else container['Id'][:12],
                    image=container['Image'],
                    status=container['State'],
                    created_at=container['Created'],
                    ports=container.get('Ports', [])
                ))

            return result
        except Exception as e:
            raise EngineError(f"Failed to list containers: {e}")

    async def list_images(self) -> List[ImageInfo]:
        """列出镜像"""
        try:
            images = self.client.images()

            result = []
            for image in images:
                # 解析镜像名称和标签
                repo_tags = image.get('RepoTags', [])
                if repo_tags and repo_tags[0] != '<none>:<none>':
                    name, tag = repo_tags[0].split(":") if ":" in repo_tags[0] else (repo_tags[0], "latest")
                else:
                    name, tag = "none", "none"

                result.append(ImageInfo(
                    id=image['Id'],
                    name=name,
                    tag=tag,
                    size=image.get('Size', 0),
                    created_at=image.get('Created', 0)
                ))

            return result
        except Exception as e:
            raise EngineError(f"Failed to list images: {e}")

    async def get_container_stats(self, container_id: str) -> Dict[str, Any]:
        """获取容器统计信息"""
        try:
            stats = self.client.stats(container_id, stream=False)

            # 解析统计信息
            cpu_stats = stats['cpu_stats']
            precpu_stats = stats['precpu_stats']
            memory_stats = stats['memory_stats']
            networks = stats['networks'] or {}

            # 计算CPU使用率
            cpu_delta = cpu_stats['cpu_usage']['total_usage'] - precpu_stats['cpu_usage']['total_usage']
            system_delta = cpu_stats['system_cpu_usage'] - precpu_stats['system_cpu_usage']
            cpu_percent = 0.0
            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * len(cpu_stats['cpu_usage']['percpu_usage']) * 100.0

            # 网络统计
            rx_bytes = sum(net.get('rx_bytes', 0) for net in networks.values())
            tx_bytes = sum(net.get('tx_bytes', 0) for net in networks.values())

            return {
                "cpu": {
                    "usage_total": cpu_stats['cpu_usage']['total_usage'],
                    "usage_percent": cpu_percent
                },
                "memory": {
                    "usage": memory_stats['usage'],
                    "limit": memory_stats.get('limit', 0),
                    "rss": memory_stats.get('stats', {}).get('rss', 0)
                },
                "network": {
                    "rx_bytes": rx_bytes,
                    "tx_bytes": tx_bytes
                }
            }
        except Exception as e:
            raise EngineError(f"Failed to get container stats for {container_id}: {e}")
