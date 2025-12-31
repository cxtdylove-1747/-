"""
Helper utilities for the performance testing framework
"""

import time
from typing import Dict, Any, Optional


def format_duration(seconds: float) -> str:
    """格式化持续时间"""
    if seconds < 1e-6:
        return f"{seconds * 1e9:.2f} ns"
    if seconds < 1e-3:
        return f"{seconds * 1e6:.2f} µs"
    if seconds < 1:
        return f"{seconds * 1e3:.3f} ms"
    if seconds < 60:
        return f"{seconds:.3f} s"
    if seconds < 3600:
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        return f"{minutes}m{remaining_seconds:.1f}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining_seconds = seconds % 60
    return f"{hours}h{minutes}m{remaining_seconds:.1f}s"


def format_bytes(bytes_value: int) -> str:
    """格式化字节数"""
    if bytes_value == 0:
        return "0 B"

    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    value = float(bytes_value)

    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"
    return f"{value:.2f} {units[unit_index]}"


def validate_engine_config(config: Dict[str, Any]) -> bool:
    """验证引擎配置"""
    required_fields = ['endpoint']

    for field in required_fields:
        if field not in config:
            return False

    # 验证endpoint格式
    endpoint = config.get('endpoint', '')
    if not endpoint:
        return False

    # 检查是否是有效的endpoint格式
    if not (endpoint.startswith('unix://') or endpoint.startswith('tcp://') or ':' in endpoint):
        return False

    return True


def calculate_percentile(data: list, percentile: float) -> float:
    """计算百分位数"""
    if not data:
        return 0.0

    data_sorted = sorted(data)
    index = int(len(data_sorted) * percentile / 100)
    if index >= len(data_sorted):
        index = len(data_sorted) - 1
    return data_sorted[index]


def calculate_moving_average(data: list, window_size: int = 5) -> list:
    """计算移动平均"""
    if len(data) < window_size:
        return data

    result = []
    for i in range(len(data)):
        start = max(0, i - window_size + 1)
        end = i + 1
        result.append(sum(data[start:end]) / (end - start))

    return result


def detect_trend(data: list) -> str:
    """检测趋势"""
    if len(data) < 3:
        return "insufficient_data"

    # 简单的线性回归趋势检测
    n = len(data)
    x = list(range(n))
    y = data

    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_xx = sum(xi * xi for xi in x)

    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)

    if slope > 0.01:
        return "increasing"
    elif slope < -0.01:
        return "decreasing"
    else:
        return "stable"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """安全除法，避免除零错误"""
    try:
        return numerator / denominator if denominator != 0 else default
    except (ZeroDivisionError, TypeError):
        return default


def merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并字典"""
    result = dict1.copy()

    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def timestamp_to_datetime(timestamp: float) -> str:
    """将时间戳转换为可读的日期时间字符串"""
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))


def generate_test_id(prefix: str = "test") -> str:
    """生成测试ID"""
    return f"{prefix}_{int(time.time() * 1000)}"


def deep_get(dictionary: Dict[str, Any], keys: str, default: Any = None) -> Any:
    """从嵌套字典中获取值"""
    keys_list = keys.split('.')
    current = dictionary

    for key in keys_list:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current
