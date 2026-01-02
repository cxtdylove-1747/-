"""
Main CLI entry point for iSulad Performance Testing Framework
"""

import asyncio
import sys
from typing import List, Optional
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from core.config import Config
from core.logger import setup_logging, get_logger
from core.exceptions import PerfTestError
from engines import BaseEngine, EngineType, ISuladEngine, DockerEngine, CRIoEngine, ContainerdEngine
from executor import BaseExecutor, ExecutorType, CRIExecutor, ClientExecutor
from processor import BaseProcessor, DataAnalyzer, StatisticsCalculator
from reporter import BaseReporter, ConsoleReporter, HTMLReporter


console = Console()
logger = get_logger()


def create_engine(engine_name: str, config: Config) -> BaseEngine:
    """创建引擎实例"""
    engine_config = config.get_engine_config(engine_name)

    if engine_name.lower() == "isulad":
        return ISuladEngine(engine_config)
    elif engine_name.lower() == "docker":
        return DockerEngine(engine_config)
    elif engine_name.lower() == "crio":
        return CRIoEngine(engine_config)
    elif engine_name.lower() == "containerd":
        return ContainerdEngine(engine_config)
    else:
        raise ValueError(f"Unsupported engine: {engine_name}")


def create_executor(executor_type: str, engine: BaseEngine, test_config) -> BaseExecutor:
    """创建执行器实例"""
    if executor_type.lower() == "cri":
        return CRIExecutor(engine, test_config)
    elif executor_type.lower() == "client":
        return ClientExecutor(engine, test_config)
    else:
        raise ValueError(f"Unsupported executor type: {executor_type}")


@click.group()
@click.option('--config', '-c', 'config_file', type=click.Path(exists=True),
              help='Configuration file path')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.pass_context
def cli(ctx, config_file, verbose):
    """iSulad Performance Testing Framework CLI"""

    # 初始化配置
    config = Config(config_file)
    ctx.obj = {'config': config}

    # 设置日志
    log_level = "DEBUG" if verbose else config.get_logging_config().get("level", "INFO")
    config.get_logging_config()["level"] = log_level
    setup_logging(config.get_logging_config())


@cli.command()
@click.argument('executor_type', type=click.Choice(['cri', 'client']))
@click.argument('engine_name', type=click.Choice(['isulad', 'docker', 'crio', 'containerd']))
@click.argument('test_name')
@click.option('--iterations', '-i', type=int, help='Number of test iterations')
@click.option('--warmup-iterations', type=int, help='Number of warmup iterations (set 0 to disable warmup)')
@click.option('--concurrency', type=int, help='Number of concurrent operations')
@click.option('--duration', type=int, help='Test duration in seconds')
@click.option('--output', '-o', type=click.Path(), help='Output file for results')
@click.option('--format', '-f', type=click.Choice(['console', 'json', 'html']),
              default='console', help='Output format')
@click.pass_context
def run(ctx, executor_type, engine_name, test_name, iterations, warmup_iterations,
        concurrency, duration, output, format):
    """Run performance tests"""
    config = ctx.obj['config']

    try:
        # 更新测试配置
        test_config = config.get_test_config(test_name)
        if iterations:
            test_config.iterations = iterations
        if warmup_iterations is not None:
            test_config.warmup_iterations = warmup_iterations
        if concurrency:
            test_config.concurrency = concurrency
        if duration:
            test_config.duration = duration

        console.print(f"[bold blue]Running {test_name} test with {engine_name} engine using {executor_type} interface[/bold blue]")

        # 创建引擎和执行器
        engine = create_engine(engine_name, config)

        if executor_type == "cri" and engine_name == "docker":
            raise ValueError("docker不是CRI运行时，不能使用CRI模式（请用 client 模式或选择 isulad/crio）")
        if executor_type == "client" and engine_name in ("crio", "containerd"):
            raise ValueError("crio/containerd 不支持 client 模式（请用 cri 模式或选择 isulad/docker）")
        executor = create_executor(executor_type, engine, test_config)

        # 运行测试
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running performance test...", total=None)

            # 异步运行测试
            loop = asyncio.get_event_loop()
            test_result = loop.run_until_complete(executor.run_test(test_name))

            progress.update(task, completed=True)

        # 处理结果
        analyzer = DataAnalyzer(baseline_engine="isulad")
        processed_data = analyzer.process([test_result])

        # 生成报告
        if format == 'console':
            reporter = ConsoleReporter()
            if output:
                reporter.report(processed_data, output)
            else:
                reporter.report(processed_data)
        elif format == 'html':
            reporter = HTMLReporter()
            output_file = output or f"{test_name}_{engine_name}_{executor_type}_report.html"
            report_path = reporter.report(processed_data, output_file)
            console.print(f"[green]HTML report saved to: {report_path}[/green]")
        elif format == 'json':
            import json
            output_file = output or f"{test_name}_{engine_name}_{executor_type}_results.json"
            output_path = Path(config.get_report_config().output_dir) / output_file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "test_result": {
                        "test_name": test_result.test_name,
                        "engine_name": test_result.engine_name,
                        "executor_type": test_result.executor_type.value,
                        "metrics": [m.__dict__ if hasattr(m, '__dict__') else m for m in test_result.metrics],
                        "summary": test_result.summary,
                        "start_time": test_result.start_time,
                        "end_time": test_result.end_time,
                        "success": test_result.success,
                        "error_message": test_result.error_message
                    }
                }, f, indent=2, ensure_ascii=False, default=str)
            console.print(f"[green]JSON results saved to: {output_path}[/green]")

        # 显示简要结果
        if test_result.success:
            console.print(f"[green]✓ Test completed successfully[/green]")
            if test_result.summary:
                ops_per_sec = test_result.summary.get('operations_per_second', 0)
                avg_duration = test_result.summary.get('avg_duration', 0)
                console.print(f"[dim]ops/s={ops_per_sec:.2f}, avg={avg_duration*1000:.2f}ms[/dim]")
        else:
            console.print(f"[red]✗ Test failed: {test_result.error_message}[/red]")

    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument('engines', nargs=-1, required=True)
@click.argument('test_name')
@click.option('--executor-type', '-e', type=click.Choice(['cri', 'client']),
              default='cri', help='Executor type')
@click.option('--iterations', '-i', type=int, help='Number of test iterations per engine')
@click.option('--warmup-iterations', type=int, help='Number of warmup iterations (set 0 to disable warmup)')
@click.option('--output', '-o', type=click.Path(), help='Output file for comparison results')
@click.option('--format', '-f', type=click.Choice(['console', 'html']),
              default='console', help='Output format')
@click.pass_context
def compare(ctx, engines, test_name, executor_type, iterations, warmup_iterations, output, format):
    """Compare performance across different engines"""
    config = ctx.obj['config']

    try:
        console.print(f"[bold blue]Comparing {test_name} performance across engines: {', '.join(engines)}[/bold blue]")

        test_results = []

        # 为每个引擎运行测试
        for engine_name in engines:
            console.print(f"[dim]Testing {engine_name}...[/dim]")

            # 更新配置
            # NOTE: use the actual test_name so per-test config like `tests.create_container` works.
            test_config = config.get_test_config(test_name)
            if iterations:
                test_config.iterations = iterations
            if warmup_iterations is not None:
                test_config.warmup_iterations = warmup_iterations

            # 创建引擎和执行器
            engine = create_engine(engine_name, config)
            executor = create_executor(executor_type, engine, test_config)

            # 运行测试
            loop = asyncio.get_event_loop()
            test_result = loop.run_until_complete(executor.run_test(test_name))
            test_results.append(test_result)

        # 处理和比较结果
        analyzer = DataAnalyzer(baseline_engine="isulad")
        processed_data = analyzer.process(test_results)

        # 生成对比报告
        if format == 'console':
            reporter = ConsoleReporter()
            if output:
                reporter.report(processed_data, output)
            else:
                reporter.report(processed_data)
        elif format == 'html':
            reporter = HTMLReporter()
            output_file = output or f"comparison_{test_name}_{'_'.join(engines)}_report.html"
            report_path = reporter.report(processed_data, output_file)
            console.print(f"[green]HTML comparison report saved to: {report_path}[/green]")

        console.print(f"[green]✓ Comparison completed for {len(engines)} engines[/green]")

    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument('engines', nargs=-1, required=True)
@click.option('--executor-type', '-e', type=click.Choice(['cri', 'client']),
              default='cri', help='Executor type')
@click.option('--suite', type=click.Choice(['standard', 'standard_offline', 'extended', 'extended_offline', 'client', 'client_offline', 'client_extended']),
              help='Benchmark suite name (defaults: cri->standard, client->client)')
@click.option('--iterations', '-i', type=int, help='Override iterations for all tests')
@click.option('--warmup-iterations', type=int, help='Override warmup iterations for all tests (set 0 to disable warmup)')
@click.option('--output', '-o', type=click.Path(), help='Output file for benchmark report')
@click.option('--format', '-f', type=click.Choice(['console', 'html']),
              default='html', help='Output format')
@click.pass_context
def bench(ctx, engines, executor_type, suite, iterations, warmup_iterations, output, format):
    """Run a benchmark suite across engines and generate a report"""
    config = ctx.obj['config']

    try:
        if suite is None:
            suite = "client_offline" if executor_type == "client" else "standard_offline"

        tests = config.get(f"benchmarks.{suite}_tests", [])
        if not tests:
            raise ValueError(f"No tests configured for suite '{suite}'. Check config: benchmarks.{suite}_tests")

        console.print(f"[bold blue]Benchmark suite '{suite}' ({executor_type}) on engines: {', '.join(engines)}[/bold blue]")

        test_results = []
        loop = asyncio.get_event_loop()

        for test_name in tests:
            for engine_name in engines:
                # compatibility guardrails
                if executor_type == "cri" and engine_name == "docker":
                    console.print(f"[yellow]Skip {test_name} on docker (docker is not a CRI runtime)[/yellow]")
                    continue
                if executor_type == "client" and engine_name in ("crio", "containerd"):
                    console.print(f"[yellow]Skip {test_name} on {engine_name} (no client mode)[/yellow]")
                    continue

                console.print(f"[dim]Running {test_name} on {engine_name}...[/dim]")

                test_config = config.get_test_config(test_name)
                if iterations:
                    test_config.iterations = iterations
                if warmup_iterations is not None:
                    test_config.warmup_iterations = warmup_iterations

                engine = create_engine(engine_name, config)
                executor = create_executor(executor_type, engine, test_config)
                test_result = loop.run_until_complete(executor.run_test(test_name))
                test_results.append(test_result)

        analyzer = DataAnalyzer(baseline_engine="isulad")
        processed_data = analyzer.process(test_results)

        if format == 'console':
            reporter = ConsoleReporter()
            if output:
                reporter.report(processed_data, output)
            else:
                reporter.report(processed_data)
        else:
            reporter = HTMLReporter()
            output_file = output or f"bench_{suite}_{executor_type}_{'_'.join(engines)}.html"
            report_path = reporter.report(processed_data, output_file)
            console.print(f"[green]HTML benchmark report saved to: {report_path}[/green]")

        console.print(f"[green]✓ Benchmark completed: {len(test_results)} test runs[/green]")

    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--format', '-f', type=click.Choice(['console', 'html']),
              default='console', help='Output format')
@click.option('--output', '-o', type=click.Path(), help='Output file')
@click.pass_context
def report(ctx, input_file, format, output):
    """Generate report from saved test results"""
    config = ctx.obj['config']

    try:
        import json

        # 加载测试结果
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 重新构造测试结果对象
        from executor.base import TestResult, ExecutorType
        from engines.base import PerformanceMetrics

        test_result_data = data['test_result']
        metrics = []
        for m in test_result_data['metrics']:
            metrics.append(PerformanceMetrics(**m))

        test_result = TestResult(
            test_name=test_result_data['test_name'],
            engine_name=test_result_data['engine_name'],
            executor_type=ExecutorType(test_result_data['executor_type']),
            metrics=metrics,
            summary=test_result_data['summary'],
            start_time=test_result_data['start_time'],
            end_time=test_result_data['end_time'],
            success=test_result_data['success'],
            error_message=test_result_data.get('error_message')
        )

        # 处理和生成报告
        analyzer = DataAnalyzer()
        processed_data = analyzer.process([test_result])

        if format == 'console':
            reporter = ConsoleReporter()
            if output:
                reporter.report(processed_data, output)
            else:
                reporter.report(processed_data)
        elif format == 'html':
            reporter = HTMLReporter()
            output_file = output or f"report_{int(test_result.start_time)}.html"
            report_path = reporter.report(processed_data, output_file)
            console.print(f"[green]HTML report saved to: {report_path}[/green]")

    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument('engine_name', type=click.Choice(['isulad', 'docker', 'crio', 'containerd']))
@click.option('--executor-type', '-e', type=click.Choice(['cri', 'client']),
              default='cri', help='Executor type')
@click.pass_context
def health(ctx, engine_name, executor_type):
    """Check engine health and connectivity"""
    config = ctx.obj['config']

    try:
        console.print(f"[bold blue]Checking health of {engine_name} engine...[/bold blue]")
        # 使用“真实执行路径”做健康检查：
        # - CRI：用 crictl 连接 endpoint
        # - client：用对应客户端命令探测
        engine_cfg = config.get_engine_config(engine_name)
        loop = asyncio.get_event_loop()
        if executor_type == "cri":
            if engine_name == "docker":
                raise ValueError("docker不是CRI运行时，不能使用CRI模式（请用 client 模式或选择 isulad/crio/containerd）")
            from executor.cri_executor import CRIExecutor
            engine = create_engine(engine_name, config)
            test_cfg = config.get_test_config("list_images")
            ex = CRIExecutor(engine, test_cfg)
            loop.run_until_complete(ex.setup())
            connected = True
        else:
            if engine_name in ("crio", "containerd"):
                raise ValueError("crio/containerd 不支持 client 模式（请用 cri 模式或选择 isulad/docker）")
            from executor.client_executor import ClientExecutor
            engine = create_engine(engine_name, config)
            test_cfg = config.get_test_config("list_images")
            ex = ClientExecutor(engine, test_cfg)
            loop.run_until_complete(ex.setup())
            connected = True

        if connected:
            console.print(f"[green]✓ {engine_name} engine is healthy and connected[/green]")

            # 显示引擎信息
            try:
                version_info = "CRI-based engine"  # 简化的版本信息
                console.print(f"[dim]Engine type: {engine_name}[/dim]")
                console.print(f"[dim]Connection endpoint: {engine_cfg.endpoint}[/dim]")
            except:
                pass
        else:
            console.print(f"[red]✗ {engine_name} engine is not accessible[/red]")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]✗ Health check failed: {e}[/red]")
        sys.exit(1)


@cli.command()
def list_engines():
    """List available container engines"""
    console.print("[bold blue]Available Container Engines:[/bold blue]")
    console.print("• isulad - iSulad container engine")
    console.print("• docker - Docker container engine")
    console.print("• crio   - CRI-O container engine (CRI)")
    console.print("• containerd - containerd engine (CRI)")


@cli.command()
def list_tests():
    """List available performance tests"""
    console.print("[bold blue]Available Performance Tests:[/bold blue]")

    console.print("\n[bold]CRI Interface Tests:[/bold]")
    cri_tests = [
        "create_container - Container creation performance",
        "start_container  - Container startup performance",
        "stop_container   - Container stop performance",
        "remove_container - Container removal performance",
        "pull_image       - Image pull performance",
        "list_containers  - Container listing performance",
        "list_images      - Image listing performance",
        "container_stats  - Container statistics retrieval performance"
    ]
    for test in cri_tests:
        console.print(f"• {test}")

    console.print("\n[bold]Client Interface Tests:[/bold]")
    client_tests = [
        "pull_image       - Image pull performance via client",
        "create_container - Container creation via client",
        "start_container  - Container startup via client",
        "stop_container   - Container stop via client",
        "remove_container - Container removal via client",
        "list_containers  - Container listing via client",
        "list_images      - Image listing via client",
        "exec_command     - Command execution in container",
        "logs             - Container logs retrieval"
    ]
    for test in client_tests:
        console.print(f"• {test}")


def main():
    """Main entry point"""
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)


if __name__ == '__main__':
    main()
