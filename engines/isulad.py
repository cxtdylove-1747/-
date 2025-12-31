"""
iSulad container engine adapter
"""

import asyncio
import time
from typing import Dict, Any, Optional, List
import grpc
import json

from .base import BaseEngine, EngineType, ContainerInfo, ImageInfo, PerformanceMetrics
from core.config import EngineConfig
from core.exceptions import EngineError, ConnectionError

# 导入CRI相关模块（需要安装cri-api）
try:
    from cri_api import api_pb2, api_pb2_grpc
except ImportError:
    # 如果没有安装CRI API，使用模拟实现
    api_pb2 = None
    api_pb2_grpc = None


class ISuladEngine(BaseEngine):
    """iSulad容器引擎适配器"""

    def __init__(self, config: EngineConfig):
        super().__init__(config)
        self.endpoint = config.endpoint
        self.timeout = config.timeout
        self.channel = None
        self.stub = None

    def get_engine_type(self) -> EngineType:
        return EngineType.ISULAD

    async def connect(self) -> bool:
        """连接到iSulad"""
        try:
            if api_pb2_grpc is None:
                raise EngineError("CRI API not available. Please install cri-api package.")

            # 创建gRPC通道
            if self.endpoint.startswith("unix://"):
                socket_path = self.endpoint.replace("unix://", "")
                self.channel = grpc.aio.insecure_channel(
                    f"unix:{socket_path}",
                    options=[
                        ('grpc.max_receive_message_length', 50 * 1024 * 1024),
                        ('grpc.max_send_message_length', 50 * 1024 * 1024),
                    ]
                )
            else:
                # TCP连接
                host, port = self.endpoint.split(":")
                self.channel = grpc.aio.insecure_channel(
                    f"{host}:{port}",
                    options=[
                        ('grpc.max_receive_message_length', 50 * 1024 * 1024),
                        ('grpc.max_send_message_length', 50 * 1024 * 1024),
                    ]
                )

            # 创建stub
            self.stub = api_pb2_grpc.RuntimeServiceStub(self.channel)

            # 测试连接
            version_request = api_pb2.VersionRequest()
            response = await asyncio.wait_for(
                self.stub.Version(version_request),
                timeout=self.timeout
            )

            self.connected = True
            return True

        except Exception as e:
            self.connected = False
            raise ConnectionError(f"Failed to connect to iSulad: {e}")

    async def disconnect(self):
        """断开连接"""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
        self.connected = False

    async def is_connected(self) -> bool:
        """检查连接状态"""
        if not self.connected or not self.stub:
            return False

        try:
            version_request = api_pb2.VersionRequest()
            await asyncio.wait_for(
                self.stub.Version(version_request),
                timeout=5
            )
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
            # 创建Pod沙箱
            pod_sandbox_config = api_pb2.PodSandboxConfig(
                metadata=api_pb2.PodSandboxMetadata(
                    name=name or f"perf-test-{int(time.time())}",
                    namespace="default",
                ),
                hostname="",
                log_directory="/tmp",
            )

            sandbox_request = api_pb2.RunPodSandboxRequest(config=pod_sandbox_config)
            sandbox_response = await self.stub.RunPodSandbox(sandbox_request)
            pod_sandbox_id = sandbox_response.pod_sandbox_id

            # 创建容器配置
            container_config = api_pb2.ContainerConfig(
                metadata=api_pb2.ContainerMetadata(
                    name=name or f"container-{int(time.time())}",
                ),
                image=api_pb2.ImageSpec(image=image),
                command=command or [],
                args=[],
                working_dir="/",
                labels={},
                annotations={},
                mounts=[],
                devices=[],
                env=[],
                log_path="",
            )

            # 创建容器
            container_request = api_pb2.CreateContainerRequest(
                pod_sandbox_id=pod_sandbox_id,
                config=container_config,
                sandbox_config=pod_sandbox_config,
            )

            container_response = await self.stub.CreateContainer(container_request)
            container_id = container_response.container_id

            end_time = time.time()

            return ContainerInfo(
                id=container_id,
                name=name or f"container-{int(time.time())}",
                image=image,
                status="created",
                created_at=start_time,
                ports=ports,
                labels={"pod_sandbox_id": pod_sandbox_id}
            )

        except Exception as e:
            end_time = time.time()
            raise EngineError(f"Failed to create container: {e}")

    async def start_container(self, container_id: str) -> bool:
        """启动容器"""
        start_time = time.time()
        try:
            request = api_pb2.StartContainerRequest(container_id=container_id)
            await self.stub.StartContainer(request)
            end_time = time.time()
            return True
        except Exception as e:
            raise EngineError(f"Failed to start container {container_id}: {e}")

    async def stop_container(self, container_id: str, timeout: int = 30) -> bool:
        """停止容器"""
        start_time = time.time()
        try:
            request = api_pb2.StopContainerRequest(
                container_id=container_id,
                timeout=timeout
            )
            await self.stub.StopContainer(request)
            end_time = time.time()
            return True
        except Exception as e:
            raise EngineError(f"Failed to stop container {container_id}: {e}")

    async def remove_container(self, container_id: str, force: bool = False) -> bool:
        """删除容器"""
        start_time = time.time()
        try:
            request = api_pb2.RemoveContainerRequest(container_id=container_id)
            await self.stub.RemoveContainer(request)
            end_time = time.time()
            return True
        except Exception as e:
            raise EngineError(f"Failed to remove container {container_id}: {e}")

    async def pull_image(self, image: str) -> ImageInfo:
        """拉取镜像"""
        start_time = time.time()
        try:
            image_spec = api_pb2.ImageSpec(image=image)
            request = api_pb2.PullImageRequest(image=image_spec)
            response = await self.stub.PullImage(request)

            # 获取镜像信息
            status_request = api_pb2.ImageStatusRequest(image=image_spec)
            status_response = await self.stub.ImageStatus(status_request)

            end_time = time.time()

            return ImageInfo(
                id=status_response.image.id,
                name=image.split(":")[0],
                tag=image.split(":")[1] if ":" in image else "latest",
                size=status_response.image.size,
                created_at=start_time
            )
        except Exception as e:
            raise EngineError(f"Failed to pull image {image}: {e}")

    async def remove_image(self, image_id: str) -> bool:
        """删除镜像"""
        try:
            image_spec = api_pb2.ImageSpec(image=image_id)
            request = api_pb2.RemoveImageRequest(image=image_spec)
            await self.stub.RemoveImage(request)
            return True
        except Exception as e:
            raise EngineError(f"Failed to remove image {image_id}: {e}")

    async def list_containers(self, all: bool = False) -> List[ContainerInfo]:
        """列出容器"""
        try:
            request = api_pb2.ListContainersRequest()
            response = await self.stub.ListContainers(request)

            containers = []
            for container in response.containers:
                containers.append(ContainerInfo(
                    id=container.id,
                    name=container.metadata.name,
                    image=container.image.image,
                    status=container.state,
                    created_at=container.created_at,
                    labels=dict(container.labels)
                ))

            return containers
        except Exception as e:
            raise EngineError(f"Failed to list containers: {e}")

    async def list_images(self) -> List[ImageInfo]:
        """列出镜像"""
        try:
            request = api_pb2.ListImagesRequest()
            response = await self.stub.ListImages(request)

            images = []
            for image in response.images:
                # 解析镜像名称和标签
                repo_tags = image.repo_tags
                if repo_tags:
                    name, tag = repo_tags[0].split(":") if ":" in repo_tags[0] else (repo_tags[0], "latest")
                else:
                    name, tag = "unknown", "latest"

                images.append(ImageInfo(
                    id=image.id,
                    name=name,
                    tag=tag,
                    size=image.size,
                    created_at=0  # CRI API可能不提供创建时间
                ))

            return images
        except Exception as e:
            raise EngineError(f"Failed to list images: {e}")

    async def get_container_stats(self, container_id: str) -> Dict[str, Any]:
        """获取容器统计信息"""
        try:
            request = api_pb2.ContainerStatsRequest(container_id=container_id)
            response = await self.stub.ContainerStats(request)

            stats = response.stats
            return {
                "cpu": {
                    "usage_total": stats.cpu.usage_core_nano_seconds,
                    "usage_percent": 0.0  # 需要计算
                },
                "memory": {
                    "usage": stats.memory.usage_bytes,
                    "working_set": stats.memory.working_set_bytes,
                    "rss": stats.memory.rss_bytes
                },
                "network": {
                    "rx_bytes": stats.network.rx_bytes,
                    "tx_bytes": stats.network.tx_bytes
                },
                "filesystem": [
                    {
                        "device": fs.device,
                        "used_bytes": fs.used_bytes,
                        "inodes_used": fs.inodes_used
                    } for fs in stats.filesystem
                ]
            }
        except Exception as e:
            raise EngineError(f"Failed to get container stats for {container_id}: {e}")
