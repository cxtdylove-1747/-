"""
CRI interface performance test executor (based on `crictl`)

This aligns with the recommended reference: https://github.com/kubernetes-sigs/cri-tools
and avoids hard dependency on protobuf stubs.
"""

import asyncio
import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

from .base import BaseExecutor, ExecutorType, TestContext
from engines.base import BaseEngine, PerformanceMetrics


@dataclass
class _CmdResult:
    returncode: int
    stdout: str
    stderr: str


class CRIExecutor(BaseExecutor):
    """CRI接口性能测试执行器（通过crictl调用CRI）"""

    def __init__(self, engine: BaseEngine, config):
        super().__init__(engine, config)
        self.runtime_endpoint = engine.config.endpoint
        self.image_endpoint = getattr(engine.config, "image_endpoint", None) or self.runtime_endpoint
        self._tmpdir: Optional[str] = None
        self._created: List[str] = []  # 记录创建的sandbox/container id

    def get_executor_type(self) -> ExecutorType:
        return ExecutorType.CRI

    async def setup(self):
        await self._check_crictl_available()
        self._tmpdir = tempfile.mkdtemp(prefix="isulad-perf-cri-")

    async def teardown(self):
        # best-effort cleanup
        try:
            await self._cleanup_created()
        finally:
            if self._tmpdir and os.path.isdir(self._tmpdir):
                try:
                    for fn in os.listdir(self._tmpdir):
                        try:
                            os.remove(os.path.join(self._tmpdir, fn))
                        except Exception:
                            pass
                    os.rmdir(self._tmpdir)
                except Exception:
                    pass
            self._tmpdir = None

    async def run_single_test(self, context: TestContext) -> List[PerformanceMetrics]:
        name = context.test_name
        if name == "pull_image":
            return [await self._crictl_pull_image("busybox:latest", warmup=context.warmup)]
        if name == "list_containers":
            return [await self._crictl_list_containers(warmup=context.warmup)]
        if name == "list_images":
            return [await self._crictl_list_images(warmup=context.warmup)]
        if name in ("create_container", "start_container", "stop_container", "remove_container"):
            return await self._cri_container_lifecycle(name, warmup=context.warmup)
        if name == "container_stats":
            return [await self._crictl_stats(warmup=context.warmup)]
        raise ValueError(f"Unknown CRI test: {name}")

    async def _run(self, args: List[str], timeout: int = 60) -> _CmdResult:
        proc = await asyncio.create_subprocess_exec(
            *args,
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

    async def _check_crictl_available(self):
        res = await self._run(["crictl", "version"], timeout=10)
        if res.returncode != 0:
            raise RuntimeError(f"crictl not available: {res.stderr.strip()}")

    def _base_args(self) -> List[str]:
        args = ["crictl", "--runtime-endpoint", self.runtime_endpoint]
        if self.image_endpoint:
            args += ["--image-endpoint", self.image_endpoint]
        return args

    async def _crictl_pull_image(self, image: str, warmup: bool) -> PerformanceMetrics:
        start = time.time()
        res = await self._run(self._base_args() + ["pull", image], timeout=max(60, self.config.timeout if hasattr(self.config, "timeout") else 60))
        end = time.time()
        return PerformanceMetrics(
            operation="pull_image",
            start_time=start,
            end_time=end,
            duration=end - start,
            success=res.returncode == 0,
            error_message=None if res.returncode == 0 else res.stderr.strip() or res.stdout.strip(),
            metadata={"image": image},
            warmup=warmup,
        )

    async def _crictl_list_containers(self, warmup: bool) -> PerformanceMetrics:
        start = time.time()
        res = await self._run(self._base_args() + ["ps", "-a"], timeout=30)
        end = time.time()
        count = 0
        if res.returncode == 0 and res.stdout.strip():
            count = max(0, len(res.stdout.strip().splitlines()) - 1)
        return PerformanceMetrics(
            operation="list_containers",
            start_time=start,
            end_time=end,
            duration=end - start,
            success=res.returncode == 0,
            error_message=None if res.returncode == 0 else res.stderr.strip(),
            metadata={"container_count": count},
            warmup=warmup,
        )

    async def _crictl_list_images(self, warmup: bool) -> PerformanceMetrics:
        start = time.time()
        res = await self._run(self._base_args() + ["images"], timeout=30)
        end = time.time()
        count = 0
        if res.returncode == 0 and res.stdout.strip():
            count = max(0, len(res.stdout.strip().splitlines()) - 1)
        return PerformanceMetrics(
            operation="list_images",
            start_time=start,
            end_time=end,
            duration=end - start,
            success=res.returncode == 0,
            error_message=None if res.returncode == 0 else res.stderr.strip(),
            metadata={"image_count": count},
            warmup=warmup,
        )

    async def _crictl_stats(self, warmup: bool) -> PerformanceMetrics:
        # `crictl stats --no-stream` may require at least one running container; we do best-effort.
        start = time.time()
        res = await self._run(self._base_args() + ["stats", "--no-stream"], timeout=30)
        end = time.time()
        return PerformanceMetrics(
            operation="container_stats",
            start_time=start,
            end_time=end,
            duration=end - start,
            success=res.returncode == 0,
            error_message=None if res.returncode == 0 else res.stderr.strip(),
            metadata={"output_lines": len(res.stdout.splitlines())},
            warmup=warmup,
        )

    def _write_json(self, name: str, obj: dict) -> str:
        assert self._tmpdir
        path = os.path.join(self._tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return path

    async def _cri_container_lifecycle(self, step: str, warmup: bool) -> List[PerformanceMetrics]:
        """
        Minimal lifecycle based on:
        - runp (pod sandbox)
        - create (container)
        - start
        - stop
        - rm
        """
        image = "busybox:latest"
        pod_name = f"perf-test-pod-{uuid.uuid4().hex[:8]}"
        ctr_name = f"perf-test-ctr-{uuid.uuid4().hex[:8]}"

        pod_cfg = {
            "metadata": {"name": pod_name, "namespace": "default", "attempt": 1},
            "log_directory": "/tmp",
            "linux": {},
        }
        ctr_cfg = {
            "metadata": {"name": ctr_name},
            "image": {"image": image},
            "command": ["sh", "-c", "echo hello && sleep 1"],
            "linux": {},
        }
        pod_path = self._write_json(f"{pod_name}.pod.json", pod_cfg)
        ctr_path = self._write_json(f"{ctr_name}.ctr.json", ctr_cfg)

        metrics: List[PerformanceMetrics] = []

        # runp
        start = time.time()
        runp = await self._run(self._base_args() + ["runp", pod_path], timeout=30)
        end = time.time()
        sandbox_id = runp.stdout.strip().splitlines()[-1].strip() if runp.returncode == 0 else ""
        metrics.append(
            PerformanceMetrics(
                operation="run_pod_sandbox",
                start_time=start,
                end_time=end,
                duration=end - start,
                success=runp.returncode == 0,
                error_message=None if runp.returncode == 0 else runp.stderr.strip() or runp.stdout.strip(),
                metadata={"pod_name": pod_name, "sandbox_id": sandbox_id},
                warmup=warmup,
            )
        )
        if runp.returncode != 0:
            return metrics
        self._created.append(sandbox_id)

        # create
        start = time.time()
        create = await self._run(self._base_args() + ["create", sandbox_id, ctr_path, pod_path], timeout=30)
        end = time.time()
        ctr_id = create.stdout.strip().splitlines()[-1].strip() if create.returncode == 0 else ""
        metrics.append(
            PerformanceMetrics(
                operation="create_container",
                start_time=start,
                end_time=end,
                duration=end - start,
                success=create.returncode == 0,
                error_message=None if create.returncode == 0 else create.stderr.strip() or create.stdout.strip(),
                metadata={"container_name": ctr_name, "container_id": ctr_id},
                warmup=warmup,
            )
        )
        if create.returncode != 0:
            return metrics
        self._created.append(ctr_id)

        if step == "create_container":
            return metrics

        # start
        start = time.time()
        start_res = await self._run(self._base_args() + ["start", ctr_id], timeout=30)
        end = time.time()
        metrics.append(
            PerformanceMetrics(
                operation="start_container",
                start_time=start,
                end_time=end,
                duration=end - start,
                success=start_res.returncode == 0,
                error_message=None if start_res.returncode == 0 else start_res.stderr.strip() or start_res.stdout.strip(),
                metadata={"container_id": ctr_id},
                warmup=warmup,
            )
        )
        if step == "start_container":
            return metrics

        # stop
        start = time.time()
        stop_res = await self._run(self._base_args() + ["stop", ctr_id], timeout=30)
        end = time.time()
        metrics.append(
            PerformanceMetrics(
                operation="stop_container",
                start_time=start,
                end_time=end,
                duration=end - start,
                success=stop_res.returncode == 0,
                error_message=None if stop_res.returncode == 0 else stop_res.stderr.strip() or stop_res.stdout.strip(),
                metadata={"container_id": ctr_id},
                warmup=warmup,
            )
        )
        if step == "stop_container":
            return metrics

        # rm
        start = time.time()
        rm_res = await self._run(self._base_args() + ["rm", ctr_id], timeout=30)
        end = time.time()
        metrics.append(
            PerformanceMetrics(
                operation="remove_container",
                start_time=start,
                end_time=end,
                duration=end - start,
                success=rm_res.returncode == 0,
                error_message=None if rm_res.returncode == 0 else rm_res.stderr.strip() or rm_res.stdout.strip(),
                metadata={"container_id": ctr_id},
                warmup=warmup,
            )
        )
        return metrics

    async def _cleanup_created(self):
        # Try to remove containers first, then pods
        ids = list(self._created)
        self._created = []
        for _id in reversed(ids):
            if not _id:
                continue
            # try rm (container) and stopp/rmp (pod) best-effort
            await self._run(self._base_args() + ["rm", _id], timeout=10)
            await self._run(self._base_args() + ["stopp", _id], timeout=10)
            await self._run(self._base_args() + ["rmp", _id], timeout=10)
