"""
Client interface performance test executor
"""

import time
import asyncio
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import uuid

from .base import BaseExecutor, ExecutorType, TestContext, PerformanceMetrics
from engines.base import BaseEngine


@dataclass
class _CmdResult:
    returncode: int
    stdout: str
    stderr: str


class ClientExecutor(BaseExecutor):
    """客户端接口性能测试执行器"""

    def __init__(self, engine: BaseEngine, config):
        super().__init__(engine, config)
        self.test_containers = []
        self.client_command = self._get_client_command()

    def get_executor_type(self) -> ExecutorType:
        return ExecutorType.CLIENT

    def _get_client_command(self) -> str:
        """获取客户端命令"""
        engine_type = self.engine.get_engine_type()

        if engine_type.value == "isulad":
            return "isula"  # iSulad客户端命令
        elif engine_type.value == "docker":
            return "docker"  # Docker客户端命令
        elif engine_type.value == "crio":
            return "crictl"  # CRI-O客户端命令
        else:
            raise ValueError(f"Unsupported engine type: {engine_type}")

    async def setup(self):
        """测试前准备"""
        # 确保客户端可用
        await self._check_client_available()

        # 清理可能存在的测试资源
        await self._cleanup_test_resources()

    async def teardown(self):
        """测试后清理"""
        await self._cleanup_test_resources()

    async def _check_client_available(self):
        """检查客户端是否可用"""
        try:
            result = await self._run_command([self.client_command, "version"])
            if result.returncode != 0:
                raise RuntimeError(f"Client {self.client_command} not available")
        except FileNotFoundError:
            raise RuntimeError(f"Client {self.client_command} not found in PATH")

    async def _cleanup_test_resources(self):
        """清理测试资源"""
        try:
            # 停止并删除测试容器
            stop_result = await self._run_command([
                self.client_command, "ps", "-a", "--format", "{{.Names}}"
            ])

            if stop_result.returncode == 0:
                container_names = [
                    line.strip() for line in stop_result.stdout.split('\n')
                    if line.strip() and line.strip().startswith("perf-test-")
                ]

                for name in container_names:
                    # 停止容器
                    await self._run_command([self.client_command, "stop", name])
                    # 删除容器
                    await self._run_command([self.client_command, "rm", name])

        except Exception:
            pass  # 忽略清理错误

    async def _run_command(self, cmd: List[str], timeout: int = 30) -> _CmdResult:
        """运行命令（异步）"""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            raise

        return _CmdResult(
            returncode=proc.returncode or 0,
            stdout=(stdout_b or b"").decode("utf-8", errors="replace"),
            stderr=(stderr_b or b"").decode("utf-8", errors="replace"),
        )

    async def run_single_test(self, context: TestContext) -> List[PerformanceMetrics]:
        """运行单个客户端测试"""
        test_name = context.test_name
        metrics = []

        try:
            if test_name == "pull_image":
                metrics.extend(await self._test_pull_image_client(context))
            elif test_name == "create_container":
                metrics.extend(await self._test_create_container_client(context))
            elif test_name == "start_container":
                metrics.extend(await self._test_start_container_client(context))
            elif test_name == "stop_container":
                metrics.extend(await self._test_stop_container_client(context))
            elif test_name == "remove_container":
                metrics.extend(await self._test_remove_container_client(context))
            elif test_name == "list_containers":
                metrics.extend(await self._test_list_containers_client(context))
            elif test_name == "list_images":
                metrics.extend(await self._test_list_images_client(context))
            elif test_name == "exec_command":
                metrics.extend(await self._test_exec_command_client(context))
            elif test_name == "logs":
                metrics.extend(await self._test_logs_client(context))
            else:
                raise ValueError(f"Unknown client test: {test_name}")

        except Exception as e:
            # 记录错误指标
            metrics.append(PerformanceMetrics(
                operation=test_name,
                start_time=time.time(),
                end_time=time.time(),
                duration=0,
                success=False,
                error_message=str(e)
            ))

        return metrics

    async def _test_pull_image_client(self, context: TestContext) -> List[PerformanceMetrics]:
        """测试客户端镜像拉取性能"""
        metrics = []

        image = getattr(self.config, "image", "busybox:latest")

        start_time = time.time()
        try:
            result = await self._run_command([self.client_command, "pull", image])
            end_time = time.time()

            success = result.returncode == 0
            metrics.append(PerformanceMetrics(
                operation="pull_image_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=success,
                error_message=result.stderr if not success else None,
                metadata={"image": image}
            ))

        except Exception as e:
            end_time = time.time()
            metrics.append(PerformanceMetrics(
                operation="pull_image_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=False,
                error_message=str(e)
            ))

        return metrics

    async def _test_create_container_client(self, context: TestContext) -> List[PerformanceMetrics]:
        """测试客户端容器创建性能"""
        metrics = []

        image = getattr(self.config, "image", "busybox:latest")
        container_name = f"perf-test-{uuid.uuid4().hex[:8]}"

        start_time = time.time()
        try:
            result = await self._run_command([
                self.client_command, "create", "--name", container_name, image, "echo", "hello"
            ])
            end_time = time.time()

            success = result.returncode == 0
            container_id = result.stdout.strip() if success else None

            metrics.append(PerformanceMetrics(
                operation="create_container_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=success,
                error_message=result.stderr if not success else None,
                metadata={
                    "container_name": container_name,
                    "container_id": container_id,
                    "image": image
                }
            ))

            if success and container_id:
                self.test_containers.append(container_name)

        except Exception as e:
            end_time = time.time()
            metrics.append(PerformanceMetrics(
                operation="create_container_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=False,
                error_message=str(e)
            ))

        return metrics

    async def _test_start_container_client(self, context: TestContext) -> List[PerformanceMetrics]:
        """测试客户端容器启动性能"""
        metrics = []

        if not self.test_containers:
            # 先创建一个容器
            create_metrics = await self._test_create_container_client(context)
            metrics.extend(create_metrics)
            if not create_metrics or not create_metrics[0].success:
                return metrics

        container_name = self.test_containers[-1]

        start_time = time.time()
        try:
            result = await self._run_command([self.client_command, "start", container_name])
            end_time = time.time()

            success = result.returncode == 0
            metrics.append(PerformanceMetrics(
                operation="start_container_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=success,
                error_message=result.stderr if not success else None,
                metadata={"container_name": container_name}
            ))

        except Exception as e:
            end_time = time.time()
            metrics.append(PerformanceMetrics(
                operation="start_container_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=False,
                error_message=str(e)
            ))

        return metrics

    async def _ensure_container_created_for_op(self, context: TestContext) -> Optional[str]:
        """
        为 stop/remove/exec/logs 等操作确保存在一个“已创建”的容器。
        注意：这里不把 create 的耗时计入调用方测试指标，避免污染 stop/remove 的统计。
        """
        if self.test_containers:
            return self.test_containers[-1]
        create_metrics = await self._test_create_container_client(context)
        if create_metrics and create_metrics[0].success and self.test_containers:
            return self.test_containers[-1]
        return None

    async def _ensure_container_started_for_op(self, context: TestContext) -> Optional[str]:
        """
        为 stop/exec/logs 等操作确保存在一个“运行中”的容器。
        注意：这里不把 start 的耗时计入调用方测试指标。
        """
        name = await self._ensure_container_created_for_op(context)
        if not name:
            return None
        try:
            await self._run_command([self.client_command, "start", name])
        except Exception:
            pass
        return name

    async def _test_stop_container_client(self, context: TestContext) -> List[PerformanceMetrics]:
        """测试客户端容器停止性能"""
        metrics = []

        container_name = await self._ensure_container_started_for_op(context)
        if not container_name:
            metrics.append(PerformanceMetrics(
                operation="stop_container_client",
                start_time=time.time(),
                end_time=time.time(),
                duration=0,
                success=False,
                error_message="No container available to stop (create/start failed)"
            ))
            return metrics

        start_time = time.time()
        try:
            result = await self._run_command([self.client_command, "stop", container_name])
            end_time = time.time()

            success = result.returncode == 0
            metrics.append(PerformanceMetrics(
                operation="stop_container_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=success,
                error_message=result.stderr if not success else None,
                metadata={"container_name": container_name}
            ))

        except Exception as e:
            end_time = time.time()
            metrics.append(PerformanceMetrics(
                operation="stop_container_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=False,
                error_message=str(e)
            ))

        return metrics

    async def _test_remove_container_client(self, context: TestContext) -> List[PerformanceMetrics]:
        """测试客户端容器删除性能"""
        metrics = []

        container_name = await self._ensure_container_created_for_op(context)
        if not container_name:
            metrics.append(PerformanceMetrics(
                operation="remove_container_client",
                start_time=time.time(),
                end_time=time.time(),
                duration=0,
                success=False,
                error_message="No container available to remove (create failed)"
            ))
            return metrics
        # remove will consume it from tracking list (best-effort)
        if self.test_containers and self.test_containers[-1] == container_name:
            self.test_containers.pop()

        start_time = time.time()
        try:
            result = await self._run_command([self.client_command, "rm", container_name])
            end_time = time.time()

            success = result.returncode == 0
            metrics.append(PerformanceMetrics(
                operation="remove_container_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=success,
                error_message=result.stderr if not success else None,
                metadata={"container_name": container_name}
            ))

        except Exception as e:
            end_time = time.time()
            metrics.append(PerformanceMetrics(
                operation="remove_container_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=False,
                error_message=str(e)
            ))

        return metrics

    async def _test_list_containers_client(self, context: TestContext) -> List[PerformanceMetrics]:
        """测试客户端列出容器性能"""
        metrics = []

        start_time = time.time()
        try:
            result = await self._run_command([self.client_command, "ps", "-a"])
            end_time = time.time()

            success = result.returncode == 0
            container_count = len(result.stdout.strip().split('\n')) - 1 if success and result.stdout.strip() else 0

            metrics.append(PerformanceMetrics(
                operation="list_containers_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=success,
                error_message=result.stderr if not success else None,
                metadata={"container_count": container_count}
            ))

        except Exception as e:
            end_time = time.time()
            metrics.append(PerformanceMetrics(
                operation="list_containers_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=False,
                error_message=str(e)
            ))

        return metrics

    async def _test_list_images_client(self, context: TestContext) -> List[PerformanceMetrics]:
        """测试客户端列出镜像性能"""
        metrics = []

        start_time = time.time()
        try:
            result = await self._run_command([self.client_command, "images"])
            end_time = time.time()

            success = result.returncode == 0
            image_count = len(result.stdout.strip().split('\n')) - 1 if success and result.stdout.strip() else 0

            metrics.append(PerformanceMetrics(
                operation="list_images_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=success,
                error_message=result.stderr if not success else None,
                metadata={"image_count": image_count}
            ))

        except Exception as e:
            end_time = time.time()
            metrics.append(PerformanceMetrics(
                operation="list_images_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=False,
                error_message=str(e)
            ))

        return metrics

    async def _test_exec_command_client(self, context: TestContext) -> List[PerformanceMetrics]:
        """测试客户端执行命令性能"""
        metrics = []

        if not self.test_containers:
            # 先创建一个运行中的容器
            create_metrics = await self._test_create_container_client(context)
            metrics.extend(create_metrics)
            if create_metrics and create_metrics[0].success:
                start_metrics = await self._test_start_container_client(context)
                metrics.extend(start_metrics)
                if not start_metrics or not start_metrics[0].success:
                    return metrics

        container_name = self.test_containers[-1]

        start_time = time.time()
        try:
            result = await self._run_command([
                self.client_command, "exec", container_name, "echo", "test"
            ])
            end_time = time.time()

            success = result.returncode == 0
            metrics.append(PerformanceMetrics(
                operation="exec_command_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=success,
                error_message=result.stderr if not success else None,
                metadata={"container_name": container_name}
            ))

        except Exception as e:
            end_time = time.time()
            metrics.append(PerformanceMetrics(
                operation="exec_command_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=False,
                error_message=str(e)
            ))

        return metrics

    async def _test_logs_client(self, context: TestContext) -> List[PerformanceMetrics]:
        """测试客户端获取日志性能"""
        metrics = []

        if not self.test_containers:
            return metrics

        container_name = self.test_containers[-1]

        start_time = time.time()
        try:
            result = await self._run_command([self.client_command, "logs", container_name])
            end_time = time.time()

            success = result.returncode == 0
            metrics.append(PerformanceMetrics(
                operation="logs_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=success,
                error_message=result.stderr if not success else None,
                metadata={"container_name": container_name}
            ))

        except Exception as e:
            end_time = time.time()
            metrics.append(PerformanceMetrics(
                operation="logs_client",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                success=False,
                error_message=str(e)
            ))

        return metrics
