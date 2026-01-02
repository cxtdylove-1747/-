"""
Data analyzer for performance test results
"""

import time
import statistics
from typing import Dict, Any, List
from collections import defaultdict

from .base import BaseProcessor, ProcessorType, ProcessedData
from executor.base import TestResult
from engines.base import PerformanceMetrics


class DataAnalyzer(BaseProcessor):
    """性能测试数据分析器"""

    def __init__(self, baseline_engine: str = ""):
        super().__init__()
        # If set and present in the comparison set, we always use it as baseline.
        self.baseline_engine = (baseline_engine or "").strip()

    def get_processor_type(self) -> ProcessorType:
        return ProcessorType.ANALYZER

    def process(self, test_results: List[TestResult]) -> ProcessedData:
        """分析测试结果数据"""
        if not self.validate_input(test_results):
            raise ValueError("Invalid test results provided")

        processed_data = {
            "summary": self._generate_overall_summary(test_results),
            "test_analysis": self._analyze_individual_tests(test_results),
            "engine_comparison": self._compare_engines(test_results),
            "performance_insights": self._generate_performance_insights(test_results),
            "anomalies": self._detect_anomalies(test_results)
        }

        return ProcessedData(
            processor_type=self.get_processor_type(),
            test_results=test_results,
            processed_data=processed_data,
            metadata=self.metadata,
            timestamp=time.time()
        )

    def _generate_overall_summary(self, test_results: List[TestResult]) -> Dict[str, Any]:
        """生成总体摘要"""
        total_tests = len(test_results)
        successful_tests = len([r for r in test_results if r.success])
        failed_tests = total_tests - successful_tests

        total_metrics = []
        total_duration = 0

        for result in test_results:
            total_metrics.extend(result.metrics)
            total_duration += (result.end_time - result.start_time)

        successful_operations = len([m for m in total_metrics if m.success])
        total_operations = len(total_metrics)

        return {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "success_rate": successful_tests / total_tests if total_tests > 0 else 0,
            "total_operations": total_operations,
            "successful_operations": successful_operations,
            "operation_success_rate": successful_operations / total_operations if total_operations > 0 else 0,
            "total_duration": total_duration,
            "avg_test_duration": total_duration / total_tests if total_tests > 0 else 0
        }

    def _analyze_individual_tests(self, test_results: List[TestResult]) -> Dict[str, Any]:
        """分析单个测试"""
        analysis = {}

        # 按测试名称分组
        tests_by_name = defaultdict(list)
        for result in test_results:
            tests_by_name[result.test_name].append(result)

        for test_name, results in tests_by_name.items():
            analysis[test_name] = self._analyze_test_group(test_name, results)

        return analysis

    def _analyze_test_group(self, test_name: str, results: List[TestResult]) -> Dict[str, Any]:
        """分析一组相同名称的测试"""
        if not results:
            return {}

        # 收集所有指标
        all_metrics = []
        for result in results:
            all_metrics.extend(result.metrics)

        if not all_metrics:
            return {"error": "No metrics available"}

        # 计算性能统计
        durations = [m.duration for m in all_metrics if m.success]
        successful_ops = len([m for m in all_metrics if m.success])
        total_ops = len(all_metrics)

        analysis = {
            "test_count": len(results),
            "total_operations": total_ops,
            "successful_operations": successful_ops,
            "success_rate": successful_ops / total_ops if total_ops > 0 else 0,
        }

        if durations:
            analysis.update({
                "avg_duration": statistics.mean(durations),
                "min_duration": min(durations),
                "max_duration": max(durations),
                "std_duration": statistics.stdev(durations) if len(durations) > 1 else 0,
                "median_duration": statistics.median(durations),
                "p95_duration": self._percentile(durations, 95),
                "p99_duration": self._percentile(durations, 99),
                "operations_per_second": len(durations) / sum(durations) if sum(durations) > 0 else 0
            })

        # 按引擎分组分析
        engines = defaultdict(list)
        for result in results:
            engines[result.engine_name].extend(result.metrics)

        analysis["engines"] = {}
        for engine_name, metrics in engines.items():
            engine_durations = [m.duration for m in metrics if m.success]
            engine_failed = len(metrics) - len(engine_durations)
            engine_entry = {
                "operation_count": len(metrics),
                "successful_count": len(engine_durations),
                "failed_count": engine_failed,
                "success_rate": (len(engine_durations) / len(metrics)) if metrics else 0,
            }
            if engine_durations:
                engine_entry.update({
                    "avg_duration": statistics.mean(engine_durations),
                    "operations_per_second": len(engine_durations) / sum(engine_durations) if sum(engine_durations) > 0 else 0,
                })
            analysis["engines"][engine_name] = engine_entry

        return analysis

    def _compare_engines(self, test_results: List[TestResult]) -> Dict[str, Any]:
        """比较不同引擎的性能"""
        if not test_results:
            return {}

        # 按引擎分组
        engines_data = defaultdict(list)
        for result in test_results:
            engines_data[result.engine_name].append(result)

        if len(engines_data) < 2:
            return {"error": "Need at least 2 engines for comparison"}

        comparison = {}

        # 获取所有测试名称
        all_test_names = set()
        for results in engines_data.values():
            for result in results:
                all_test_names.add(result.test_name)

        # 对每个测试进行引擎间比较
        for test_name in all_test_names:
            comparison[test_name] = self._compare_test_across_engines(test_name, engines_data)

        return comparison

    def _compare_test_across_engines(self, test_name: str, engines_data: Dict[str, List[TestResult]]) -> Dict[str, Any]:
        """比较单个测试在不同引擎间的性能"""
        engine_metrics = {}

        for engine_name, results in engines_data.items():
            # 找到该引擎的这个测试结果
            test_result = next((r for r in results if r.test_name == test_name), None)
            if test_result and test_result.metrics:
                durations = [m.duration for m in test_result.metrics if m.success]
                if durations:
                    engine_metrics[engine_name] = {
                        "avg_duration": statistics.mean(durations),
                        "operations_per_second": len(durations) / sum(durations),
                        "success_rate": len(durations) / len(test_result.metrics)
                    }

        if len(engine_metrics) < 2:
            return {"error": "Insufficient data for comparison"}

        # 计算相对性能
        if self.baseline_engine and self.baseline_engine in engine_metrics:
            baseline_engine = self.baseline_engine
        else:
            baseline_engine = min(engine_metrics.keys(), key=lambda x: engine_metrics[x]["avg_duration"])
        baseline_avg = engine_metrics[baseline_engine]["avg_duration"]

        relative_performance = {}
        for engine, metrics in engine_metrics.items():
            relative_performance[engine] = {
                "relative_duration": metrics["avg_duration"] / baseline_avg,
                "performance_ratio": baseline_avg / metrics["avg_duration"],
                "is_faster": metrics["avg_duration"] < baseline_avg
            }

        return {
            "engine_metrics": engine_metrics,
            "baseline_engine": baseline_engine,
            "relative_performance": relative_performance
        }

    def _generate_performance_insights(self, test_results: List[TestResult]) -> Dict[str, Any]:
        """生成性能洞察"""
        insights = {
            "bottlenecks": [],
            "recommendations": [],
            "trends": []
        }

        # 分析瓶颈
        for result in test_results:
            if result.metrics:
                durations = [m.duration for m in result.metrics if m.success]
                if durations:
                    avg_duration = statistics.mean(durations)
                    if avg_duration > 1.0:  # 超过1秒的操作
                        insights["bottlenecks"].append({
                            "test": result.test_name,
                            "engine": result.engine_name,
                            "avg_duration": avg_duration,
                            "severity": "high" if avg_duration > 5.0 else "medium"
                        })

        # 生成建议
        if insights["bottlenecks"]:
            insights["recommendations"].append(
                "Consider optimizing slow operations identified in bottlenecks"
            )

        # 分析趋势
        if len(test_results) > 1:
            # 检查性能是否随时间变化
            sorted_results = sorted(test_results, key=lambda x: x.start_time)
            first_half = sorted_results[:len(sorted_results)//2]
            second_half = sorted_results[len(sorted_results)//2:]

            first_avg = self._calculate_avg_duration(first_half)
            second_avg = self._calculate_avg_duration(second_half)

            if first_avg > 0 and second_avg > 0:
                trend = (second_avg - first_avg) / first_avg
                if abs(trend) > 0.1:  # 超过10%的变化
                    insights["trends"].append({
                        "type": "performance_trend",
                        "description": f"Performance {'improved' if trend < 0 else 'degraded'} by {abs(trend)*100:.1f}%",
                        "change_percent": trend * 100
                    })

        return insights

    def _detect_anomalies(self, test_results: List[TestResult]) -> List[Dict[str, Any]]:
        """检测异常"""
        anomalies = []

        for result in test_results:
            if not result.metrics:
                continue

            durations = [m.duration for m in result.metrics if m.success]
            if len(durations) < 3:  # 需要足够的样本
                continue

            mean_duration = statistics.mean(durations)
            stdev_duration = statistics.stdev(durations)

            # 检测异常值（超出3个标准差）
            threshold = mean_duration + 3 * stdev_duration

            for i, duration in enumerate(durations):
                if duration > threshold:
                    anomalies.append({
                        "type": "outlier_duration",
                        "test": result.test_name,
                        "engine": result.engine_name,
                        "iteration": i,
                        "duration": duration,
                        "mean_duration": mean_duration,
                        "deviation_sigma": (duration - mean_duration) / stdev_duration
                    })

        return anomalies

    def _calculate_avg_duration(self, results: List[TestResult]) -> float:
        """计算一组测试结果的平均持续时间"""
        total_duration = 0
        count = 0

        for result in results:
            if result.metrics:
                durations = [m.duration for m in result.metrics if m.success]
                if durations:
                    total_duration += sum(durations)
                    count += len(durations)

        return total_duration / count if count > 0 else 0

    def _percentile(self, data: List[float], percentile: float) -> float:
        """计算百分位数"""
        if not data:
            return 0.0

        data_sorted = sorted(data)
        index = int(len(data_sorted) * percentile / 100)
        if index >= len(data_sorted):
            index = len(data_sorted) - 1
        return data_sorted[index]
