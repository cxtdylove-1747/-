"""
Main CLI entry point for iSulad Performance Testing Framework
"""

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from core.config import Config
from core.logger import setup_logging, get_logger
from engines import create_engine, list_engines as list_engines_registry
from executor import create_executor, list_executors as list_executors_registry
from processor import DataAnalyzer
from reporter import ConsoleReporter, HTMLReporter
from core.envinfo import collect_env_info
from utils.artifacts import make_run_dir, write_json

console = Console()
logger = get_logger()


def run_async(coro):
    """Run an async coroutine from sync click commands."""
    return asyncio.run(coro)


def _engine_choice() -> click.Choice:
    return click.Choice(sorted(list_engines_registry().keys()), case_sensitive=False)


def _executor_choice() -> click.Choice:
    return click.Choice(sorted(list_executors_registry().keys()), case_sensitive=False)


@click.group()
@click.option("--config", "-c", "config_file", type=click.Path(exists=True), help="Configuration file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, config_file, verbose):
    """iSulad Performance Testing Framework CLI"""
    config = Config(config_file)
    ctx.obj = {"config": config}

    log_level = "DEBUG" if verbose else config.get_logging_config().get("level", "INFO")
    config.get_logging_config()["level"] = log_level
    setup_logging(config.get_logging_config())


def _save_artifacts(run_dir: Path, processed_data, raw: dict):
    """Persist standardized artifacts to run_dir."""
    meta = processed_data.metadata or {}
    write_json(run_dir / "meta.json", meta)
    if isinstance(meta, dict) and "env" in meta:
        write_json(run_dir / "env.json", meta.get("env"))

    write_json(run_dir / "raw_results.json", raw)
    write_json(
        run_dir / "processed.json",
        {
            "processed_data": processed_data.processed_data,
            "metadata": processed_data.metadata,
            "timestamp": processed_data.timestamp,
        },
    )


@cli.command()
@click.argument("executor_type", type=_executor_choice())
@click.argument("engine_name", type=_engine_choice())
@click.argument("test_name")
@click.option("--iterations", "-i", type=int, help="Number of test iterations")
@click.option("--warmup-iterations", type=int, help="Number of warmup iterations (set 0 to disable warmup)")
@click.option("--concurrency", type=int, help="Number of concurrent operations")
@click.option("--duration", type=int, help="Test duration in seconds")
@click.option("--output", "-o", type=click.Path(), help="Output file for results (report path)")
@click.option("--format", "-f", type=click.Choice(["console", "json", "html"]), default="console", help="Output format")
@click.pass_context
def run(ctx, executor_type, engine_name, test_name, iterations, warmup_iterations, concurrency, duration, output, format):
    """Run performance tests"""
    config = ctx.obj["config"]

    try:
        test_config = config.get_test_config(test_name)
        if iterations:
            test_config.iterations = iterations
        if warmup_iterations is not None:
            test_config.warmup_iterations = warmup_iterations
        if concurrency:
            test_config.concurrency = concurrency
        if duration:
            test_config.duration = duration

        console.print(
            f"[bold blue]Running {test_name} test with {engine_name} engine using {executor_type} interface[/bold blue]"
        )

        if executor_type == "cri" and engine_name == "docker":
            raise ValueError("docker不是CRI运行时，不能使用CRI模式（请用 client 模式或选择 isulad/crio/containerd）")
        if executor_type == "client" and engine_name in ("crio", "containerd"):
            raise ValueError("crio/containerd 不支持 client 模式（请用 cri 模式或选择 isulad/docker）")

        engine_cfg = config.get_engine_config(engine_name)
        engine = create_engine(engine_name, engine_cfg)
        executor = create_executor(executor_type, engine, test_config)

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            task = progress.add_task("Running performance test...", total=None)
            test_result = run_async(executor.run_test(test_name))
            progress.update(task, completed=True)

        analyzer = DataAnalyzer(baseline_engine="isulad")
        analyzer.set_metadata(
            "run_config",
            {
                "mode": "run",
                "executor_type": executor_type,
                "engines": [engine_name],
                "test_name": test_name,
                "iterations": test_config.iterations,
                "warmup_iterations": test_config.warmup_iterations,
                "concurrency": test_config.concurrency,
                "duration": test_config.duration,
                "default_image": getattr(test_config, "image", ""),
                "cri_lifecycle_image": getattr(test_config, "cri_lifecycle_image", ""),
                "cri_host_network": getattr(test_config, "cri_host_network", None),
            },
        )
        analyzer.set_metadata(
            "env",
            collect_env_info(
                engines=[engine_name],
                cri_endpoints={engine_name: engine.config.endpoint} if executor_type == "cri" else {},
            ),
        )
        processed_data = analyzer.process([test_result])

        report_cfg = config.get_report_config()
        run_dir = make_run_dir(
            base_dir=report_cfg.output_dir,
            mode="run",
            executor_type=executor_type,
            engines=[engine_name],
            test_name=test_name,
        )
        _save_artifacts(run_dir, processed_data, {"test_result": test_result})

        if format == "console":
            reporter = ConsoleReporter()
            if output:
                reporter.report(processed_data, output)
            else:
                reporter.report(processed_data)
        elif format == "html":
            reporter = HTMLReporter()
            output_file = output or str(Path(run_dir.name) / "report.html")
            report_path = reporter.report(processed_data, output_file)
            console.print(f"[green]HTML report saved to: {str(run_dir / 'report.html')}[/green]")
        elif format == "json":
            output_path = Path(output) if output else (run_dir / "result.json")
            write_json(output_path, {"test_result": test_result})
            console.print(f"[green]JSON results saved to: {str(output_path)}[/green]")

        console.print(f"[green]Artifacts saved to: {str(run_dir)}[/green]")

        if test_result.success:
            console.print("[green]✓ Test completed successfully[/green]")
            if test_result.summary:
                ops_per_sec = test_result.summary.get("operations_per_second", 0)
                avg_duration = test_result.summary.get("avg_duration", 0)
                console.print(f"[dim]ops/s={ops_per_sec:.2f}, avg={avg_duration*1000:.2f}ms[/dim]")
        else:
            console.print(f"[red]✗ Test failed: {test_result.error_message}[/red]")

    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("engines", nargs=-1, required=True)
@click.argument("test_name")
@click.option("--executor-type", "-e", type=_executor_choice(), default="cri", help="Executor type")
@click.option("--iterations", "-i", type=int, help="Number of test iterations per engine")
@click.option("--warmup-iterations", type=int, help="Number of warmup iterations (set 0 to disable warmup)")
@click.option("--output", "-o", type=click.Path(), help="Output file for comparison report")
@click.option("--format", "-f", type=click.Choice(["console", "html"]), default="console", help="Output format")
@click.pass_context
def compare(ctx, engines, test_name, executor_type, iterations, warmup_iterations, output, format):
    """Compare performance across different engines"""
    config = ctx.obj["config"]

    try:
        console.print(f"[bold blue]Comparing {test_name} across engines: {', '.join(engines)}[/bold blue]")

        test_results = []
        for engine_name in engines:
            console.print(f"[dim]Testing {engine_name}...[/dim]")

            if executor_type == "cri" and engine_name == "docker":
                console.print("[yellow]Skip docker in CRI mode (docker is not a CRI runtime)[/yellow]")
                continue
            if executor_type == "client" and engine_name in ("crio", "containerd"):
                console.print(f"[yellow]Skip {engine_name} in client mode (no client interface)[/yellow]")
                continue

            test_config = config.get_test_config(test_name)
            if iterations:
                test_config.iterations = iterations
            if warmup_iterations is not None:
                test_config.warmup_iterations = warmup_iterations

            engine_cfg = config.get_engine_config(engine_name)
            engine = create_engine(engine_name, engine_cfg)
            executor = create_executor(executor_type, engine, test_config)

            test_result = run_async(executor.run_test(test_name))
            test_results.append(test_result)

        analyzer = DataAnalyzer(baseline_engine="isulad")
        analyzer.set_metadata(
            "run_config",
            {
                "mode": "compare",
                "executor_type": executor_type,
                "engines": list(engines),
                "test_name": test_name,
                "iterations": iterations,
                "warmup_iterations": warmup_iterations,
            },
        )
        cri_eps = {}
        if executor_type == "cri":
            for r in test_results:
                try:
                    cri_eps[r.engine_name] = config.get_engine_config(r.engine_name).endpoint
                except Exception:
                    pass
        analyzer.set_metadata("env", collect_env_info(engines=list(engines), cri_endpoints=cri_eps))
        processed_data = analyzer.process(test_results)

        report_cfg = config.get_report_config()
        run_dir = make_run_dir(
            base_dir=report_cfg.output_dir,
            mode="compare",
            executor_type=executor_type,
            engines=list(engines),
            test_name=test_name,
        )
        _save_artifacts(run_dir, processed_data, {"test_results": test_results})

        if format == "console":
            reporter = ConsoleReporter()
            if output:
                reporter.report(processed_data, output)
            else:
                reporter.report(processed_data)
        elif format == "html":
            reporter = HTMLReporter()
            output_file = output or str(Path(run_dir.name) / "report.html")
            report_path = reporter.report(processed_data, output_file)
            console.print(f"[green]HTML comparison report saved to: {str(run_dir / 'report.html')}[/green]")

        console.print(f"[green]Artifacts saved to: {str(run_dir)}[/green]")

    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("engines", nargs=-1, required=True)
@click.option("--executor-type", "-e", type=_executor_choice(), default="cri", help="Executor type")
@click.option(
    "--suite",
    type=click.Choice(
        ["standard", "standard_offline", "extended", "extended_offline", "client", "client_offline", "client_extended"]
    ),
    help="Benchmark suite name (defaults: cri->standard, client->client)",
)
@click.option("--iterations", "-i", type=int, help="Override iterations for all tests")
@click.option("--warmup-iterations", type=int, help="Override warmup iterations for all tests (set 0 to disable warmup)")
@click.option("--concurrency-levels", type=str, help='Comma-separated concurrency levels (e.g. "1,2,4,8")')
@click.option("--output", "-o", type=click.Path(), help="Output file for benchmark report")
@click.option("--format", "-f", type=click.Choice(["console", "html"]), default="html", help="Output format")
@click.pass_context
def bench(ctx, engines, executor_type, suite, iterations, warmup_iterations, concurrency_levels, output, format):
    """Run a benchmark suite across engines and generate a report"""
    config = ctx.obj["config"]

    try:
        if suite is None:
            suite = "client_offline" if executor_type == "client" else "standard_offline"

        tests = config.get(f"benchmarks.{suite}_tests", [])
        if not tests:
            raise ValueError(f"No tests configured for suite '{suite}'. Check config: benchmarks.{suite}_tests")

        console.print(f"[bold blue]Benchmark suite '{suite}' ({executor_type}) on engines: {', '.join(engines)}[/bold blue]")

        test_results = []

        for test_name in tests:
            for engine_name in engines:
                if executor_type == "cri" and engine_name == "docker":
                    console.print(f"[yellow]Skip {test_name} on docker (docker is not a CRI runtime)[/yellow]")
                    continue
                if executor_type == "client" and engine_name in ("crio", "containerd"):
                    console.print(f"[yellow]Skip {test_name} on {engine_name} (no client mode)[/yellow]")
                    continue

                console.print(f"[dim]Running {test_name} on {engine_name}...[/dim]")

                base_test_config = config.get_test_config(test_name)
                if iterations:
                    base_test_config.iterations = iterations
                if warmup_iterations is not None:
                    base_test_config.warmup_iterations = warmup_iterations

                # Optional concurrency sweep
                if concurrency_levels:
                    levels = []
                    for part in concurrency_levels.split(","):
                        part = part.strip()
                        if not part:
                            continue
                        try:
                            v = int(part)
                            if v > 0:
                                levels.append(v)
                        except Exception:
                            continue
                    if not levels:
                        raise ValueError("Invalid --concurrency-levels. Example: --concurrency-levels 1,2,4,8")
                else:
                    levels = [int(getattr(base_test_config, "concurrency", 1) or 1)]

                for c in levels:
                    test_config = config.get_test_config(test_name)
                    if iterations:
                        test_config.iterations = iterations
                    if warmup_iterations is not None:
                        test_config.warmup_iterations = warmup_iterations
                    test_config.concurrency = c

                    engine_cfg = config.get_engine_config(engine_name)
                    engine = create_engine(engine_name, engine_cfg)
                    executor = create_executor(executor_type, engine, test_config)

                    test_result = run_async(executor.run_test(test_name))
                    test_results.append(test_result)

        analyzer = DataAnalyzer(baseline_engine="isulad")
        analyzer.set_metadata(
            "run_config",
            {
                "mode": "bench",
                "executor_type": executor_type,
                "suite": suite,
                "engines": list(engines),
                "iterations": iterations,
                "warmup_iterations": warmup_iterations,
                "concurrency_levels": concurrency_levels,
            },
        )
        cri_eps = {}
        if executor_type == "cri":
            for e in engines:
                try:
                    cri_eps[str(e)] = config.get_engine_config(str(e)).endpoint
                except Exception:
                    pass
        analyzer.set_metadata("env", collect_env_info(engines=list(engines), cri_endpoints=cri_eps))
        processed_data = analyzer.process(test_results)

        report_cfg = config.get_report_config()
        run_dir = make_run_dir(
            base_dir=report_cfg.output_dir,
            mode="bench",
            executor_type=executor_type,
            engines=list(engines),
            suite=suite,
        )
        _save_artifacts(run_dir, processed_data, {"test_results": test_results})

        if format == "console":
            reporter = ConsoleReporter()
            if output:
                reporter.report(processed_data, output)
            else:
                reporter.report(processed_data)
        else:
            reporter = HTMLReporter()
            output_file = output or str(Path(run_dir.name) / "report.html")
            report_path = reporter.report(processed_data, output_file)
            console.print(f"[green]HTML benchmark report saved to: {str(run_dir / 'report.html')}[/green]")

        console.print(f"[green]Artifacts saved to: {str(run_dir)}[/green]")

    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("engine_name", type=_engine_choice())
@click.option("--executor-type", "-e", type=_executor_choice(), default="cri", help="Executor type")
@click.pass_context
def health(ctx, engine_name, executor_type):
    """Check engine health and connectivity"""
    config = ctx.obj["config"]

    try:
        console.print(f"[bold blue]Checking health of {engine_name} engine...[/bold blue]")

        if executor_type == "cri" and engine_name == "docker":
            raise ValueError("docker不是CRI运行时，不能使用CRI模式（请用 client 模式或选择 isulad/crio/containerd）")
        if executor_type == "client" and engine_name in ("crio", "containerd"):
            raise ValueError("crio/containerd 不支持 client 模式（请用 cri 模式或选择 isulad/docker）")

        engine_cfg = config.get_engine_config(engine_name)
        engine = create_engine(engine_name, engine_cfg)

        test_cfg = config.get_test_config("list_images")
        ex = create_executor(executor_type, engine, test_cfg)

        run_async(ex.setup())

        console.print(f"[green]✓ {engine_name} engine is healthy and connected[/green]")
        console.print(f"[dim]Engine type: {engine_name}[/dim]")
        console.print(f"[dim]Connection endpoint: {engine_cfg.endpoint}[/dim]")

    except Exception as e:
        console.print(f"[red]✗ Health check failed: {e}[/red]")
        sys.exit(1)


@cli.command("list-engines")
def list_engines_cmd():
    """List available container engines"""
    console.print("[bold blue]Available Container Engines:[/bold blue]")
    for name in sorted(list_engines_registry().keys()):
        console.print(f"• {name}")


@cli.command("list-executors")
def list_executors_cmd():
    """List available executors"""
    console.print("[bold blue]Available Executors:[/bold blue]")
    for name in sorted(list_executors_registry().keys()):
        console.print(f"• {name}")


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


if __name__ == "__main__":
    main()
