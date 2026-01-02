"""
Base executor interface for performance tests
"""

import abc
import asyncio
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from core.config import TestConfig
from core.exceptions import ExecutorError
from engines.base import BaseEngine, PerformanceMetrics


class ExecutorType(Enum):
    """执行器类型枚举"""
    CRI = "cri"
    CLIENT = "client"


@dataclass
class TestResult:
    """测试结果"""
    test_name: str
    engine_name: str
    executor_type: ExecutorType
    metrics: List[PerformanceMetrics]
    summary: Dict[str, Any]
    start_time: float
    end_time: float
    success: bool
    error_message: Optional[str] = None


@dataclass
class TestContext:
    """测试上下文"""
    test_name: str
    engine: BaseEngine
    config: TestConfig
    iteration: int
    warmup: bool = False


class BaseExecutor(abc.ABC):
    """性能测试执行器基础接口"""

    def __init__(self, engine: BaseEngine, config: TestConfig):
        self.engine = engine
        self.config = config
        self._progress_callback: Optional[Callable[[str, int, int], None]] = None

    def set_progress_callback(self, callback: Callable[[str, int, int], None]):
        """设置进度回调函数"""
        self._progress_callback = callback

    @abc.abstractmethod
    async def setup(self):
        """测试前准备"""
        pass

    @abc.abstractmethod
    async def teardown(self):
        """测试后清理"""
        pass

    @abc.abstractmethod
    async def run_single_test(self, context: TestContext) -> List[PerformanceMetrics]:
        """运行单个测试"""
        pass

    @abc.abstractmethod
    def get_executor_type(self) -> ExecutorType:
        """获取执行器类型"""
        pass

    async def run_test(self, test_name: str) -> TestResult:
        """运行完整测试"""
        start_time = time.time()

        try:
            # 准备阶段
            await self.setup()

            # 并发模式（优先）
            if getattr(self.config, "concurrency", 1) and self.config.concurrency > 1:
                result = await self.run_concurrent_test(test_name, self.config.concurrency)
                return result

            metrics = []

            # 预热阶段
            if self.config.warmup_iterations > 0:
                for i in range(self.config.warmup_iterations):
                    context = TestContext(
                        test_name=test_name,
                        engine=self.engine,
                        config=self.config,
                        iteration=i,
                        warmup=True
                    )
                    warmup_metrics = await self.run_single_test(context)
                    for m in warmup_metrics:
                        m.warmup = True
                    metrics.extend(warmup_metrics)

                    if self._progress_callback:
                        self._progress_callback(f"Warmup {test_name}", i + 1, self.config.warmup_iterations)

            # 正式测试阶段
            for i in range(self.config.iterations):
                context = TestContext(
                    test_name=test_name,
                    engine=self.engine,
                    config=self.config,
                    iteration=i,
                    warmup=False
                )
                test_metrics = await self.run_single_test(context)
                metrics.extend(test_metrics)

                if self._progress_callback:
                    self._progress_callback(f"Testing {test_name}", i + 1, self.config.iterations)

            # 清理阶段
            await self.teardown()

            end_time = time.time()

            # 生成摘要
            summary = self._generate_summary(metrics)

            # 只要存在失败迭代，就认为 test 失败（更符合“性能测试是否通过”的直觉）
            # 注意：此前 success=True 仅代表流程跑完，容易导致报告误判。
            success = True
            if not summary:
                success = False
            else:
                failed = summary.get("failed_iterations", 0)
                success = failed == 0

            return TestResult(
                test_name=test_name,
                engine_name=self.engine.config.name,
                executor_type=self.get_executor_type(),
                metrics=metrics,
                summary=summary,
                start_time=start_time,
                end_time=end_time,
                success=success
            )

        except Exception as e:
            end_time = time.time()
            await self.teardown()

            return TestResult(
                test_name=test_name,
                engine_name=self.engine.config.name,
                executor_type=self.get_executor_type(),
                metrics=[],
                summary={},
                start_time=start_time,
                end_time=end_time,
                success=False,
                error_message=str(e)
            )

    def _generate_summary(self, metrics: List[PerformanceMetrics]) -> Dict[str, Any]:
        """生成测试摘要"""
        if not metrics:
            return {}

        # 过滤出正式测试的指标（非预热）
        test_metrics = [m for m in metrics if not getattr(m, 'warmup', False)]

        if not test_metrics:
            return {}

        durations = [m.duration for m in test_metrics]
        successful = [m for m in test_metrics if m.success]
        failed = [m for m in test_metrics if not m.success]

        return {
            "total_iterations": len(test_metrics),
            "successful_iterations": len(successful),
            "failed_iterations": len(failed),
            "success_rate": len(successful) / len(test_metrics) if test_metrics else 0,
            "avg_duration": sum(durations) / len(durations),
            "min_duration": min(durations),
            "max_duration": max(durations),
            "p50_duration": self._percentile(durations, 50),
            "p95_duration": self._percentile(durations, 95),
            "p99_duration": self._percentile(durations, 99),
            "total_time": sum(durations),
            "operations_per_second": len(test_metrics) / sum(durations) if durations else 0
        }

    def _percentile(self, data: List[float], percentile: float) -> float:
        """计算百分位数"""
        if not data:
            return 0.0

        data_sorted = sorted(data)
        index = int(len(data_sorted) * percentile / 100)
        if index >= len(data_sorted):
            index = len(data_sorted) - 1
        return data_sorted[index]

    async def run_concurrent_test(self, test_name: str, concurrency: int) -> TestResult:
        """运行并发测试"""
        start_time = time.time()

        try:
            await self.setup()

            # 创建并发任务
            tasks = []
            for i in range(concurrency):
                task = asyncio.create_task(self._run_concurrent_iteration(test_name, i))
                tasks.append(task)

            # 等待所有任务完成
            results = await asyncio.gather(*tasks, return_exceptions=True)

            await self.teardown()

            end_time = time.time()

            # 处理结果
            all_metrics = []
            errors = []

            for result in results:
                if isinstance(result, Exception):
                    errors.append(str(result))
                elif isinstance(result, list):
                    all_metrics.extend(result)

            summary = self._generate_summary(all_metrics)

            success = (len(errors) == 0)
            if summary:
                success = success and (summary.get("failed_iterations", 0) == 0)
            else:
                success = False

            return TestResult(
                test_name=f"{test_name}_concurrent_{concurrency}",
                engine_name=self.engine.config.name,
                executor_type=self.get_executor_type(),
                metrics=all_metrics,
                summary=summary,
                start_time=start_time,
                end_time=end_time,
                success=success,
                error_message=f"Concurrent test errors: {errors}" if errors else None
            )

        except Exception as e:
            end_time = time.time()
            await self.teardown()

            return TestResult(
                test_name=f"{test_name}_concurrent_{concurrency}",
                engine_name=self.engine.config.name,
                executor_type=self.get_executor_type(),
                metrics=[],
                summary={},
                start_time=start_time,
                end_time=end_time,
                success=False,
                error_message=str(e)
            )

    async def _run_concurrent_iteration(self, test_name: str, task_id: int) -> List[PerformanceMetrics]:
        """运行单个并发迭代"""
        metrics = []

        for i in range(self.config.iterations):
            context = TestContext(
                test_name=f"{test_name}_task_{task_id}",
                engine=self.engine,
                config=self.config,
                iteration=i,
                warmup=False
            )
            test_metrics = await self.run_single_test(context)
            metrics.extend(test_metrics)

        return metrics
