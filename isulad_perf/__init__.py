"""
iSulad Performance Testing Framework

A comprehensive performance testing framework for iSulad container engine
with support for CRI and Client interfaces, and multi-engine comparisons.
"""

__version__ = "0.1.0"
__author__ = "Competition Team"
__description__ = "Performance testing framework for iSulad container engine"

from core import Config, get_logger, PerfTestError, EngineError, ConfigError
from engines import BaseEngine, EngineType, ISuladEngine, DockerEngine, CRIoEngine
from executor import BaseExecutor, ExecutorType, CRIExecutor, ClientExecutor
from processor import BaseProcessor, DataAnalyzer, StatisticsCalculator
from reporter import BaseReporter, ConsoleReporter, HTMLReporter

__all__ = [
    # Core
    'Config', 'get_logger', 'PerfTestError', 'EngineError', 'ConfigError',

    # Engines
    'BaseEngine', 'EngineType', 'ISuladEngine', 'DockerEngine', 'CRIoEngine',

    # Executors
    'BaseExecutor', 'ExecutorType', 'CRIExecutor', 'ClientExecutor',

    # Processors
    'BaseProcessor', 'DataAnalyzer', 'StatisticsCalculator',

    # Reporters
    'BaseReporter', 'ConsoleReporter', 'HTMLReporter'
]
