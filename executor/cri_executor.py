"""
CRI interface performance test executor (based on `crictl`)

This aligns with the recommended reference: https://github.com/kubernetes-sigs/cri-tools
and avoids hard dependency on protobuf stubs.
"""

import asyncio
import json
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .base import BaseExecutor, ExecutorType, TestContext
from core.logger import get_logger
from engines.base import BaseEngine, PerformanceMetrics

logger = get_logger(__name__)


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
        # Record created resources with type so we don't call wrong CRI verbs on IDs.
        # kind: "pod" | "container"
        self._created: List[Tuple[str, str]] = []
        # allow overriding crictl binary (e.g. use an older crictl for CRI v1alpha2)
        self.crictl_bin = os.environ.get("CRICTL_BIN", "crictl")

    def get_executor_type(self) -> ExecutorType:
        return ExecutorType.CRI

    async def setup(self):
        await self._check_crictl_available()
        self._tmpdir = tempfile.mkdtemp(prefix="isulad-perf-cri-")

    async def teardown(self):
        # best-effort cleanup
        try:
            await self._cleanup_created()
        except Exception as e:
            # Never fail a performance test because cleanup hangs/fails.
            logger.warning(f"CRI cleanup failed (ignored): {e}")
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
        image = getattr(self.config, "image", "busybox:latest")
        if name == "pull_image":
            return [await self._crictl_pull_image(image, warmup=context.warmup)]
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
        logger.debug(f"Run command (timeout={timeout}s): {' '.join(args)}")
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
            # Raise with useful context; asyncio.TimeoutError is often an "empty" exception.
            raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(args)}")
        return _CmdResult(
            returncode=proc.returncode or 0,
            stdout=(stdout_b or b"").decode("utf-8", errors="replace"),
            stderr=(stderr_b or b"").decode("utf-8", errors="replace"),
        )

    async def _check_crictl_available(self):
        if shutil.which(self.crictl_bin) is None:
            raise RuntimeError(f"{self.crictl_bin} not found in PATH (set CRICTL_BIN if needed)")
        # IMPORTANT:
        # Always validate against the configured endpoint. `crictl version` without endpoints will try
        # default endpoints and may hang or succeed against a different runtime (e.g. containerd),
        # which makes isulad tests silently fail later.
        try:
            # Keep this fast; we mainly want to verify the endpoint is responsive.
            res = await self._run(self._base_args(timeout_override_seconds=5) + ["version"], timeout=10)
        except asyncio.TimeoutError as e:
            raise RuntimeError(
                f"{self.crictl_bin} version timed out (endpoint={self.runtime_endpoint}, timeout=10s)"
            ) from e
        if res.returncode != 0:
            raise RuntimeError(
                f"{self.crictl_bin} not available for endpoint={self.runtime_endpoint}: "
                f"{(res.stderr or res.stdout).strip()}"
            )

    def _base_args(self, timeout_override_seconds: Optional[int] = None) -> List[str]:
        # Always pass crictl's own timeout; relying only on subprocess timeout makes debugging harder
        # and can leave crictl hanging.
        timeout_s = timeout_override_seconds if timeout_override_seconds is not None else int(getattr(self.engine.config, "timeout", 30))
        args = [self.crictl_bin, "--timeout", f"{timeout_s}s", "--runtime-endpoint", self.runtime_endpoint]
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
        image = getattr(self.config, "image", "busybox:latest")
        pod_name = f"perf-test-pod-{uuid.uuid4().hex[:8]}"
        ctr_name = f"perf-test-ctr-{uuid.uuid4().hex[:8]}"
        pod_uid = uuid.uuid4().hex

        # IMPORTANT:
        # Some CRI runtimes (observed on iSulad) behave badly if:
        # - PodSandbox metadata.uid is empty
        # - log_directory is a generic system directory like "/tmp"
        # - container log_path is empty
        #
        # Use a unique log_directory and a non-empty log_path to avoid symlink errors like:
        # "failed to create symbolic link /tmp to the container log file .../console.log"
        log_dir = f"/tmp/isulad-perf/pods/{pod_uid}"
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            # best-effort; runtime may still create it
            pass

        pod_cfg = {
            "metadata": {"name": pod_name, "namespace": "default", "attempt": 1, "uid": pod_uid},
            "log_directory": log_dir,
            "linux": {},
        }
        # Keep the container alive once started; otherwise start/stop/remove can race with a short-lived process.
        # This significantly improves stability and success rate in benchmarks.
        ctr_cfg = {
            "metadata": {"name": ctr_name},
            "image": {"image": image},
            "command": ["sh", "-c", "echo hello; tail -f /dev/null"],
            "log_path": f"{ctr_name}.log",
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
        self._created.append(("pod", sandbox_id))

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
        self._created.append(("container", ctr_id))

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
        # Give container a brief moment to enter Running state to avoid flakiness.
        await asyncio.sleep(0.1)
        start = time.time()
        stop_res = await self._run(self._base_args() + ["stop", ctr_id], timeout=30)
        if stop_res.returncode != 0:
            # Best-effort retry once to handle state races.
            await asyncio.sleep(0.2)
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
        if rm_res.returncode != 0:
            await asyncio.sleep(0.2)
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
        """
        Best-effort cleanup.
        IMPORTANT: Must never raise, otherwise the whole test is marked failed even if metrics exist.
        """
        items = list(self._created)
        self._created = []

        # Use short timeouts for cleanup to avoid hanging on buggy runtime states.
        base = self._base_args(timeout_override_seconds=5)

        for kind, _id in reversed(items):
            if not _id:
                continue
            try:
                if kind == "container":
                    # Container: stop (best-effort) then rm. Some runs keep the container running.
                    await self._run(base + ["stop", _id], timeout=10)
                    await self._run(base + ["rm", _id], timeout=10)
                elif kind == "pod":
                    # PodSandbox: stopp then rmp.
                    await self._run(base + ["stopp", _id], timeout=10)
                    await self._run(base + ["rmp", _id], timeout=10)
                else:
                    # Fallback: try common ops
                    await self._run(base + ["rm", _id], timeout=5)
                    await self._run(base + ["stopp", _id], timeout=5)
                    await self._run(base + ["rmp", _id], timeout=5)
            except Exception as e:
                logger.debug(f"Ignore cleanup error for {kind}({_id}): {e}")
