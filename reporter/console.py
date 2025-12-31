"""
Console result reporter
"""

import json
from typing import Dict, Any, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.layout import Layout

from .base import BaseReporter, ReporterType
from processor.base import ProcessedData


class ConsoleReporter(BaseReporter):
    """控制台结果展示器"""

    def __init__(self, output_dir: str = "./results"):
        super().__init__(output_dir)
        self.console = Console()

    def get_reporter_type(self) -> ReporterType:
        return ReporterType.CONSOLE

    def report(self, processed_data: ProcessedData, output_file: Optional[str] = None) -> str:
        """生成控制台报告"""
        self._display_header(processed_data)
        self._display_summary(processed_data)
        self._display_test_analysis(processed_data)
        self._display_engine_comparison(processed_data)
        self._display_performance_insights(processed_data)

        # 如果指定了输出文件，也保存为文本格式
        if output_file:
            self._save_to_file(processed_data, output_file)

        return "Console report displayed"

    def _display_header(self, processed_data: ProcessedData):
        """显示报告头部"""
        title = Text("iSulad Performance Test Report", style="bold magenta")
        subtitle = f"Generated at {processed_data.timestamp:.0f}"

        self.console.print(Panel(title, subtitle=subtitle, border_style="blue"))

    def _display_summary(self, processed_data: ProcessedData):
        """显示总体摘要"""
        data = processed_data.processed_data

        if "summary" not in data:
            return

        summary = data["summary"]

        # 创建摘要表格
        table = Table(title="Overall Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Tests", str(summary.get("total_tests", 0)))
        table.add_row("Successful Tests", str(summary.get("successful_tests", 0)))
        table.add_row("Failed Tests", str(summary.get("failed_tests", 0)))
        table.add_row("Success Rate", f"{summary.get('success_rate', 0)*100:.1f}%")
        table.add_row("Total Operations", str(summary.get("total_operations", 0)))
        table.add_row("Successful Operations", str(summary.get("successful_operations", 0)))
        table.add_row("Operation Success Rate", f"{summary.get('operation_success_rate', 0)*100:.1f}%")
        table.add_row("Total Duration", self._format_duration(summary.get("total_duration", 0.0)))
        table.add_row("Average Test Duration", self._format_duration(summary.get("avg_test_duration", 0.0)))

        self.console.print(table)
        self.console.print()

    def _display_test_analysis(self, processed_data: ProcessedData):
        """显示测试分析"""
        data = processed_data.processed_data

        if "test_analysis" not in data:
            return

        analysis = data["test_analysis"]

        for test_name, test_data in analysis.items():
            if isinstance(test_data, dict) and "error" not in test_data:
                table = Table(title=f"Test Analysis: {test_name}")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")

                table.add_row("Test Count", str(test_data.get("test_count", 0)))
                table.add_row("Total Operations", str(test_data.get("total_operations", 0)))
                table.add_row("Successful Operations", str(test_data.get("successful_operations", 0)))
                table.add_row("Success Rate", f"{test_data.get('success_rate', 0)*100:.1f}%")

                if "avg_duration" in test_data:
                    table.add_row("Average Duration", self._format_duration(test_data.get("avg_duration", 0.0)))
                    table.add_row("Min Duration", self._format_duration(test_data.get("min_duration", 0.0)))
                    table.add_row("Max Duration", self._format_duration(test_data.get("max_duration", 0.0)))
                    table.add_row("Std Deviation", self._format_duration(test_data.get("std_duration", 0.0)))
                    table.add_row("Median Duration", self._format_duration(test_data.get("median_duration", 0.0)))
                    table.add_row("95th Percentile", self._format_duration(test_data.get("p95_duration", 0.0)))
                    table.add_row("99th Percentile", self._format_duration(test_data.get("p99_duration", 0.0)))
                    table.add_row("Operations/Second", self._format_number(test_data.get("operations_per_second", 0.0), 2))

                self.console.print(table)

                # 显示引擎对比
                if "engines" in test_data:
                    self._display_engine_breakdown(test_data["engines"])

                self.console.print()

    def _display_engine_breakdown(self, engines: Dict[str, Any]):
        """显示引擎细分"""
        table = Table(title="Engine Breakdown")
        table.add_column("Engine", style="cyan")
        table.add_column("Operations", style="green")
        table.add_column("Successful", style="green")
        table.add_column("Avg Duration", style="yellow")
        table.add_column("Ops/Sec", style="yellow")

        for engine_name, metrics in engines.items():
            table.add_row(
                engine_name,
                str(metrics.get("operation_count", 0)),
                str(metrics.get("successful_count", 0)),
                self._format_duration(metrics.get("avg_duration", 0.0)),
                self._format_number(metrics.get("operations_per_second", 0.0), 2),
            )

        self.console.print(table)

    def _display_engine_comparison(self, processed_data: ProcessedData):
        """显示引擎对比"""
        data = processed_data.processed_data

        if "engine_comparison" not in data:
            return

        comparison = data["engine_comparison"]

        for test_name, test_comparison in comparison.items():
            if isinstance(test_comparison, dict) and "error" not in test_comparison:
                table = Table(title=f"Engine Comparison: {test_name}")
                table.add_column("Engine", style="cyan")
                table.add_column("Avg Duration", style="yellow")
                table.add_column("Ops/Sec", style="yellow")
                table.add_column("Success Rate", style="green")
                table.add_column("Relative Perf", style="magenta")

                baseline_engine = test_comparison.get("baseline_engine")
                relative_perf = test_comparison.get("relative_performance", {})

                for engine_name, metrics in test_comparison.get("engine_metrics", {}).items():
                    relative = relative_perf.get(engine_name, {})
                    perf_indicator = ".2f" if relative.get("is_faster", False) else ".2f"

                    table.add_row(
                        f"{engine_name} {'(baseline)' if engine_name == baseline_engine else ''}",
                        self._format_duration(metrics.get("avg_duration", 0.0)),
                        self._format_number(metrics.get("operations_per_second", 0.0), 2),
                        f"{metrics.get('success_rate', 0)*100:.1f}%",
                        self._format_number(relative.get("performance_ratio", 1.0), 2) + "x",
                    )

                self.console.print(table)
                self.console.print()

    def _display_performance_insights(self, processed_data: ProcessedData):
        """显示性能洞察"""
        data = processed_data.processed_data

        if "performance_insights" not in data:
            return

        insights = data["performance_insights"]

        # 显示瓶颈
        if insights.get("bottlenecks"):
            table = Table(title="Performance Bottlenecks")
            table.add_column("Test", style="red")
            table.add_column("Engine", style="red")
            table.add_column("Avg Duration", style="red")
            table.add_column("Severity", style="red")

            for bottleneck in insights["bottlenecks"]:
                table.add_row(
                    bottleneck["test"],
                    bottleneck["engine"],
                    self._format_duration(bottleneck.get("avg_duration", 0.0)),
                    bottleneck["severity"]
                )

            self.console.print(table)
            self.console.print()

        # 显示建议
        if insights.get("recommendations"):
            recommendations_panel = Panel(
                "\n".join(f"• {rec}" for rec in insights["recommendations"]),
                title="Recommendations",
                border_style="yellow"
            )
            self.console.print(recommendations_panel)
            self.console.print()

        # 显示趋势
        if insights.get("trends"):
            trends_panel = Panel(
                "\n".join(f"• {trend['description']}" for trend in insights["trends"]),
                title="Performance Trends",
                border_style="blue"
            )
            self.console.print(trends_panel)
            self.console.print()

        # 显示异常
        if "anomalies" in data and data["anomalies"]:
            table = Table(title="Detected Anomalies")
            table.add_column("Type", style="red")
            table.add_column("Test", style="red")
            table.add_column("Engine", style="red")
            table.add_column("Iteration", style="red")
            table.add_column("Details", style="red")

            for anomaly in data["anomalies"][:10]:  # 最多显示10个异常
                table.add_row(
                    anomaly["type"],
                    anomaly["test"],
                    anomaly["engine"],
                    str(anomaly["iteration"]),
                    f"Duration: {anomaly['duration']:.4f}s ({anomaly['deviation_sigma']:.1f}σ from mean)"
                )

            self.console.print(table)

    def _save_to_file(self, processed_data: ProcessedData, output_file: str):
        """保存到文件"""
        output_path = self._get_output_path(output_file)

        # 将处理后的数据保存为JSON格式
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": processed_data.timestamp,
                "processed_data": processed_data.processed_data,
                "metadata": processed_data.metadata
            }, f, indent=2, ensure_ascii=False)

        self.console.print(f"Report saved to: {output_path}")
