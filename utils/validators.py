"""
Validation utilities for the performance testing framework
"""

import os
import subprocess
from typing import Dict, Any, Optional

from core.exceptions import ValidationError


def validate_test_config(config: Dict[str, Any]) -> bool:
    """验证测试配置"""
    required_fields = ['iterations', 'concurrency']

    for field in required_fields:
        if field not in config:
            raise ValidationError(f"Missing required field: {field}")

    # 验证数值范围
    if config.get('iterations', 0) <= 0:
        raise ValidationError("iterations must be greater than 0")

    if config.get('concurrency', 0) <= 0:
        raise ValidationError("concurrency must be greater than 0")

    if config.get('duration', 0) < 0:
        raise ValidationError("duration must be non-negative")

    return True


def validate_engine_availability(engine_name: str, endpoint: str) -> bool:
    """验证引擎可用性"""
    try:
        if engine_name.lower() == "docker":
            return _check_docker_availability(endpoint)
        elif engine_name.lower() == "isulad":
            return _check_isulad_availability(endpoint)
        elif engine_name.lower() == "crio":
            return _check_crio_availability(endpoint)
        else:
            raise ValidationError(f"Unsupported engine: {engine_name}")
    except Exception as e:
        raise ValidationError(f"Engine validation failed: {e}")


def _check_docker_availability(endpoint: str) -> bool:
    """检查Docker可用性"""
    try:
        if endpoint.startswith("unix://"):
            socket_path = endpoint.replace("unix://", "")
            if not os.path.exists(socket_path):
                return False

            # 尝试连接Docker socket
            import docker
            client = docker.APIClient(base_url=endpoint)
            client.ping()
            return True
        else:
            # TCP连接检查
            import docker
            client = docker.APIClient(base_url=endpoint)
            client.ping()
            return True
    except Exception:
        return False


def _check_isulad_availability(endpoint: str) -> bool:
    """检查iSulad可用性"""
    try:
        if endpoint.startswith("unix://"):
            socket_path = endpoint.replace("unix://", "")
            if not os.path.exists(socket_path):
                return False

            # 尝试使用isula命令检查
            result = subprocess.run(
                ["isula", "version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        else:
            # 对于TCP连接，暂时返回True（需要更复杂的检查）
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False


def _check_crio_availability(endpoint: str) -> bool:
    """检查CRI-O可用性"""
    try:
        if endpoint.startswith("unix://"):
            socket_path = endpoint.replace("unix://", "")
            if not os.path.exists(socket_path):
                return False

            # 尝试使用crictl命令检查
            result = subprocess.run(
                ["crictl", "version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        else:
            # 对于TCP连接，暂时返回True
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False


def validate_output_directory(output_dir: str) -> bool:
    """验证输出目录"""
    try:
        os.makedirs(output_dir, exist_ok=True)

        # 检查是否可写
        test_file = os.path.join(output_dir, ".write_test")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)

        return True
    except (OSError, PermissionError):
        raise ValidationError(f"Output directory is not writable: {output_dir}")


def validate_test_name(test_name: str) -> bool:
    """验证测试名称"""
    valid_tests = [
        # CRI tests
        "create_container", "start_container", "stop_container", "remove_container",
        "pull_image", "list_containers", "list_images", "container_stats",
        # Client tests
        "exec_command", "logs"
    ]

    if test_name not in valid_tests:
        raise ValidationError(f"Unknown test name: {test_name}. Valid tests: {', '.join(valid_tests)}")

    return True


def validate_concurrency_value(concurrency: int, max_concurrency: int = 100) -> bool:
    """验证并发数值"""
    if concurrency <= 0:
        raise ValidationError("Concurrency must be greater than 0")

    if concurrency > max_concurrency:
        raise ValidationError(f"Concurrency cannot exceed {max_concurrency}")

    return True


def validate_iterations_value(iterations: int, max_iterations: int = 10000) -> bool:
    """验证迭代次数"""
    if iterations <= 0:
        raise ValidationError("Iterations must be greater than 0")

    if iterations > max_iterations:
        raise ValidationError(f"Iterations cannot exceed {max_iterations}")

    return True


def validate_duration_value(duration: int, max_duration: int = 3600) -> bool:
    """验证持续时间"""
    if duration < 0:
        raise ValidationError("Duration cannot be negative")

    if duration > max_duration:
        raise ValidationError(f"Duration cannot exceed {max_duration} seconds")

    return True
