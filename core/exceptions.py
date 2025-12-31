"""
Custom exceptions for iSulad Performance Testing Framework
"""


class PerfTestError(Exception):
    """性能测试基础异常"""
    pass


class ConfigError(PerfTestError):
    """配置相关异常"""
    pass


class EngineError(PerfTestError):
    """引擎相关异常"""
    pass


class ExecutorError(PerfTestError):
    """执行器相关异常"""
    pass


class ProcessorError(PerfTestError):
    """处理器相关异常"""
    pass


class ReporterError(PerfTestError):
    """报告器相关异常"""
    pass


class ValidationError(PerfTestError):
    """验证相关异常"""
    pass


class TimeoutError(PerfTestError):
    """超时异常"""
    pass


class ConnectionError(PerfTestError):
    """连接异常"""
    pass
