"""
Statistics calculator for performance test results
"""

import time
import statistics
import numpy as np
from typing import Dict, Any, List

from .base import BaseProcessor, ProcessorType, ProcessedData
from executor.base import TestResult
from engines.base import PerformanceMetrics


class StatisticsCalculator(BaseProcessor):
    """统计计算器"""

    def get_processor_type(self) -> ProcessorType:
        return ProcessorType.STATISTICS

    def process(self, test_results: List[TestResult]) -> ProcessedData:
        """计算统计数据"""
        if not self.validate_input(test_results):
            raise ValueError("Invalid test results provided")

        processed_data = {
            "basic_statistics": self._calculate_basic_statistics(test_results),
            "distribution_analysis": self._calculate_distribution_analysis(test_results),
            "correlation_analysis": self._calculate_correlation_analysis(test_results),
            "reliability_metrics": self._calculate_reliability_metrics(test_results),
            "performance_distribution": self._calculate_performance_distribution(test_results)
        }

        return ProcessedData(
            processor_type=self.get_processor_type(),
            test_results=test_results,
            processed_data=processed_data,
            metadata=self.metadata,
            timestamp=time.time()
        )

    def _calculate_basic_statistics(self, test_results: List[TestResult]) -> Dict[str, Any]:
        """计算基础统计数据"""
        all_durations = []
        successful_durations = []
        failed_count = 0
        total_count = 0

        for result in test_results:
            for metric in result.metrics:
                total_count += 1
                all_durations.append(metric.duration)
                if metric.success:
                    successful_durations.append(metric.duration)
                else:
                    failed_count += 1

        stats_data = {
            "total_operations": total_count,
            "successful_operations": len(successful_durations),
            "failed_operations": failed_count,
            "success_rate": len(successful_durations) / total_count if total_count > 0 else 0
        }

        if successful_durations:
            stats_data.update({
                "duration_stats": {
                    "mean": statistics.mean(successful_durations),
                    "median": statistics.median(successful_durations),
                    "mode": statistics.mode(successful_durations) if len(set(successful_durations)) > 1 else successful_durations[0],
                    "std_dev": statistics.stdev(successful_durations) if len(successful_durations) > 1 else 0,
                    "variance": statistics.variance(successful_durations) if len(successful_durations) > 1 else 0,
                    "min": min(successful_durations),
                    "max": max(successful_durations),
                    "range": max(successful_durations) - min(successful_durations),
                    "quartiles": self._calculate_quartiles(successful_durations),
                    "percentiles": self._calculate_percentiles(successful_durations)
                }
            })

        return stats_data

    def _calculate_quartiles(self, data: List[float]) -> Dict[str, float]:
        """计算四分位数"""
        if not data:
            return {}

        sorted_data = sorted(data)
        n = len(sorted_data)

        q1_index = int(n * 0.25)
        q2_index = int(n * 0.5)
        q3_index = int(n * 0.75)

        return {
            "q1": sorted_data[q1_index],
            "q2": sorted_data[q2_index],  # 中位数
            "q3": sorted_data[q3_index],
            "iqr": sorted_data[q3_index] - sorted_data[q1_index]  # 四分位距
        }

    def _calculate_percentiles(self, data: List[float]) -> Dict[str, float]:
        """计算百分位数"""
        if not data:
            return {}

        sorted_data = sorted(data)
        percentiles = [50, 75, 90, 95, 99, 99.9]

        result = {}
        for p in percentiles:
            index = int(len(sorted_data) * p / 100)
            if index >= len(sorted_data):
                index = len(sorted_data) - 1
            result[f"p{p}"] = sorted_data[index]

        return result

    def _calculate_distribution_analysis(self, test_results: List[TestResult]) -> Dict[str, Any]:
        """计算分布分析"""
        successful_durations = []

        for result in test_results:
            for metric in result.metrics:
                if metric.success:
                    successful_durations.append(metric.duration)

        if len(successful_durations) < 3:
            return {"error": "Insufficient data for distribution analysis"}

        arr = np.array(successful_durations, dtype=float)
        mu = float(arr.mean())
        sigma = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0

        # 轻量级：不强依赖scipy，做一个简单的JB统计量用于参考（非严格检验）
        skewness = float(self._skewness(arr))
        kurtosis = float(self._kurtosis_excess(arr))
        jb = float(len(arr) / 6.0 * (skewness ** 2 + 0.25 * (kurtosis ** 2)))
        normality_test = {
            "test": "jarque_bera_proxy",
            "statistic": jb,
            "note": "proxy only (no p-value without scipy); use for relative comparison",
        }

        distribution_fits = {"normal": {"mu": mu, "sigma": sigma}}

        return {
            "normality_test": normality_test,
            "distribution_fits": distribution_fits,
            "skewness": skewness,
            "kurtosis": kurtosis,
            "distribution_shape": self._classify_distribution(skewness, kurtosis)
        }

    def _skewness(self, arr: np.ndarray) -> float:
        if arr.size < 3:
            return 0.0
        mu = arr.mean()
        m2 = np.mean((arr - mu) ** 2)
        m3 = np.mean((arr - mu) ** 3)
        if m2 <= 0:
            return 0.0
        return m3 / (m2 ** 1.5)

    def _kurtosis_excess(self, arr: np.ndarray) -> float:
        if arr.size < 4:
            return 0.0
        mu = arr.mean()
        m2 = np.mean((arr - mu) ** 2)
        m4 = np.mean((arr - mu) ** 4)
        if m2 <= 0:
            return 0.0
        return m4 / (m2 ** 2) - 3.0

    def _classify_distribution(self, skewness: float, kurtosis: float) -> str:
        """根据偏度和峰度分类分布"""
        if abs(skewness) < 0.5 and abs(kurtosis) < 0.5:
            return "approximately_normal"
        elif skewness > 1:
            return "right_skewed"
        elif skewness < -1:
            return "left_skewed"
        elif kurtosis > 1:
            return "heavy_tailed"
        elif kurtosis < -1:
            return "light_tailed"
        else:
            return "moderately_skewed"

    def _calculate_correlation_analysis(self, test_results: List[TestResult]) -> Dict[str, Any]:
        """计算相关性分析"""
        # 按引擎分组数据
        engine_data = {}
        for result in test_results:
            if result.engine_name not in engine_data:
                engine_data[result.engine_name] = []
            engine_data[result.engine_name].extend(result.metrics)

        if len(engine_data) < 2:
            return {"error": "Need at least 2 engines for correlation analysis"}

        # 计算每个引擎的平均性能指标
        engine_metrics = {}
        for engine, metrics in engine_data.items():
            durations = [m.duration for m in metrics if m.success]
            if durations:
                engine_metrics[engine] = {
                    "avg_duration": statistics.mean(durations),
                    "success_rate": len(durations) / len(metrics),
                    "throughput": len(durations) / sum(durations) if sum(durations) > 0 else 0
                }

        # 计算相关性矩阵
        correlation_matrix = {}
        engines = list(engine_metrics.keys())

        for i, engine1 in enumerate(engines):
            correlation_matrix[engine1] = {}
            for j, engine2 in enumerate(engines):
                if i != j:
                    corr = self._calculate_engine_correlation(
                        engine_metrics[engine1],
                        engine_metrics[engine2]
                    )
                    correlation_matrix[engine1][engine2] = corr

        return {
            "engine_metrics": engine_metrics,
            "correlation_matrix": correlation_matrix,
            "correlation_summary": self._summarize_correlations(correlation_matrix)
        }

    def _calculate_engine_correlation(self, metrics1: Dict[str, float], metrics2: Dict[str, float]) -> Dict[str, float]:
        """计算两个引擎之间的相关性"""
        correlations = {}

        # 计算每个指标的相关性
        for key in metrics1.keys():
            if key in metrics2:
                # 这里简化处理，实际应该是时间序列相关性
                # 现在只是比较差异
                diff = abs(metrics1[key] - metrics2[key])
                max_val = max(abs(metrics1[key]), abs(metrics2[key]))
                if max_val > 0:
                    similarity = 1 - (diff / max_val)
                    correlations[key] = similarity
                else:
                    correlations[key] = 1.0

        return correlations

    def _summarize_correlations(self, correlation_matrix: Dict[str, Dict[str, Dict[str, float]]]) -> Dict[str, Any]:
        """总结相关性分析结果"""
        summary = {
            "strong_correlations": [],
            "weak_correlations": [],
            "average_correlation": 0.0
        }

        total_corr = 0
        count = 0

        for engine1, correlations in correlation_matrix.items():
            for engine2, metrics_corr in correlations.items():
                for metric, corr_value in metrics_corr.items():
                    total_corr += corr_value
                    count += 1

                    if corr_value > 0.8:
                        summary["strong_correlations"].append({
                            "engines": [engine1, engine2],
                            "metric": metric,
                            "correlation": corr_value
                        })
                    elif corr_value < 0.3:
                        summary["weak_correlations"].append({
                            "engines": [engine1, engine2],
                            "metric": metric,
                            "correlation": corr_value
                        })

        if count > 0:
            summary["average_correlation"] = total_corr / count

        return summary

    def _calculate_reliability_metrics(self, test_results: List[TestResult]) -> Dict[str, Any]:
        """计算可靠性指标"""
        reliability = {
            "mtbf": 0.0,  # Mean Time Between Failures
            "mttr": 0.0,  # Mean Time To Repair
            "availability": 0.0,
            "failure_rate": 0.0
        }

        total_operations = 0
        failed_operations = 0
        total_time = 0
        failure_intervals = []

        last_failure_time = None

        for result in test_results:
            result_duration = result.end_time - result.start_time
            total_time += result_duration

            for metric in result.metrics:
                total_operations += 1
                if not metric.success:
                    failed_operations += 1

                    # 记录故障间隔
                    if last_failure_time is not None:
                        interval = metric.start_time - last_failure_time
                        failure_intervals.append(interval)
                    last_failure_time = metric.start_time

        if total_operations > 0:
            reliability["failure_rate"] = failed_operations / total_operations

        if total_time > 0:
            reliability["availability"] = (total_operations - failed_operations) / total_operations

        if failure_intervals:
            reliability["mtbf"] = statistics.mean(failure_intervals)

        # MTTR这里简化计算，实际需要更复杂的故障恢复时间数据
        if failed_operations > 0 and total_time > 0:
            reliability["mttr"] = total_time / failed_operations

        return reliability

    def _calculate_performance_distribution(self, test_results: List[TestResult]) -> Dict[str, Any]:
        """计算性能分布"""
        # 按操作类型分组性能数据
        operation_performance = {}

        for result in test_results:
            for metric in result.metrics:
                operation = metric.operation
                if operation not in operation_performance:
                    operation_performance[operation] = []
                operation_performance[operation].append(metric.duration)

        distribution = {}
        for operation, durations in operation_performance.items():
            if len(durations) >= 3:
                distribution[operation] = {
                    "histogram_bins": self._create_histogram(durations),
                    "distribution_stats": self._calculate_distribution_stats(durations),
                    "outliers": self._detect_outliers(durations)
                }

        return distribution

    def _create_histogram(self, data: List[float], bins: int = 10) -> Dict[str, Any]:
        """创建直方图"""
        if not data:
            return {}

        hist, bin_edges = np.histogram(data, bins=bins)

        return {
            "bins": bins,
            "counts": hist.tolist(),
            "bin_edges": bin_edges.tolist(),
            "bin_centers": [(bin_edges[i] + bin_edges[i+1])/2 for i in range(len(bin_edges)-1)]
        }

    def _calculate_distribution_stats(self, data: List[float]) -> Dict[str, Any]:
        """计算分布统计"""
        return {
            "mean": statistics.mean(data),
            "std_dev": statistics.stdev(data) if len(data) > 1 else 0,
            "cv": statistics.stdev(data) / statistics.mean(data) if len(data) > 1 and statistics.mean(data) != 0 else 0,  # 变异系数
            "data_points": len(data)
        }

    def _detect_outliers(self, data: List[float], threshold: float = 3.0) -> List[float]:
        """检测异常值"""
        if len(data) < 3:
            return []

        mean_val = statistics.mean(data)
        std_dev = statistics.stdev(data)

        outliers = []
        for value in data:
            z_score = abs(value - mean_val) / std_dev if std_dev > 0 else 0
            if z_score > threshold:
                outliers.append(value)

        return outliers
