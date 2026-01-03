"""
Configuration management for iSulad Performance Testing Framework
"""

import os
import yaml
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EngineConfig:
    """引擎配置"""
    name: str
    endpoint: str
    timeout: int = 30
    retries: int = 3
    version: str = "latest"


@dataclass
class TestConfig:
    """测试配置"""
    name: str
    iterations: int = 10
    concurrency: int = 1
    duration: int = 60
    warmup_iterations: int = 5
    # 默认使用的镜像名（离线环境可改为 busybox:local 等）
    image: str = "busybox:latest"
    # CRI 生命周期类测试建议使用更稳定的镜像（例如 pause），避免短命进程导致 start/stop/remove 竞态失败
    cri_lifecycle_image: str = ""
    # CRI PodSandbox 是否使用 hostNetwork（NamespaceMode=NODE=2），可跳过 CNI，提升离线/虚拟机环境稳定性
    cri_host_network: bool = True


@dataclass
class ReportConfig:
    """报告配置"""
    output_dir: str = "./results"
    formats: list = None
    include_charts: bool = True
    include_raw_data: bool = False

    def __post_init__(self):
        if self.formats is None:
            self.formats = ["console", "json"]


class Config:
    """配置管理器"""

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or self._find_config_file()
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _find_config_file(self) -> str:
        """查找配置文件"""
        # 优先级: 当前目录 -> 用户家目录 -> 默认配置
        search_paths = [
            Path.cwd() / "config" / "default.yaml",
            Path.home() / ".isulad-perf" / "config.yaml",
            Path(__file__).parent.parent / "config" / "default.yaml"
        ]

        for path in search_paths:
            if path.exists():
                return str(path)

        # 如果都没有找到，使用默认配置
        return str(Path(__file__).parent.parent / "config" / "default.yaml")

    def _load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f) or {}
            else:
                self._config = self._get_default_config()
        except Exception as e:
            print(f"Warning: Failed to load config file {self.config_file}: {e}")
            self._config = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "engines": {
                "isulad": {
                    "endpoint": "unix:///var/run/isulad.sock",
                    "timeout": 30,
                    "retries": 3
                },
                "docker": {
                    "endpoint": "unix:///var/run/docker.sock",
                    "timeout": 30,
                    "retries": 3
                },
                "crio": {
                    "endpoint": "unix:///var/run/crio/crio.sock",
                    "timeout": 30,
                    "retries": 3
                },
                "containerd": {
                    "endpoint": "unix:///run/containerd/containerd.sock",
                    "timeout": 30,
                    "retries": 3
                }
            },
            "tests": {
                "default_iterations": 10,
                "default_concurrency": 1,
                "default_duration": 60,
                "warmup_iterations": 5
            },
            "report": {
                "output_dir": "./results",
                "formats": ["console", "json"],
                "include_charts": True,
                "include_raw_data": False
            },
            "logging": {
                "level": "INFO",
                "file": "isulad-perf.log",
                "max_size": "10MB",
                "backup_count": 5
            }
        }

    def get_engine_config(self, engine_name: str) -> EngineConfig:
        """获取引擎配置"""
        engine_cfg = self._config.get("engines", {}).get(engine_name, {})
        return EngineConfig(
            name=engine_name,
            endpoint=engine_cfg.get("endpoint", ""),
            timeout=engine_cfg.get("timeout", 30),
            retries=engine_cfg.get("retries", 3),
            version=engine_cfg.get("version", "latest")
        )

    def get_test_config(self, test_name: str = "default") -> TestConfig:
        """获取测试配置"""
        tests_cfg = self._config.get("tests", {}) or {}
        # 默认值
        base = {
            "iterations": tests_cfg.get("default_iterations", 10),
            "concurrency": tests_cfg.get("default_concurrency", 1),
            "duration": tests_cfg.get("default_duration", 60),
            "warmup_iterations": tests_cfg.get("warmup_iterations", 5),
            "image": tests_cfg.get("default_image", "busybox:latest"),
            "cri_lifecycle_image": tests_cfg.get("cri_lifecycle_image", ""),
            "cri_host_network": bool(tests_cfg.get("cri_host_network", True)),
        }
        # 按测试名覆盖（支持 tests: { create_container: {iterations: 20, ...} }）
        per_test = tests_cfg.get(test_name, {}) if isinstance(tests_cfg.get(test_name, {}), dict) else {}
        base.update({k: v for k, v in per_test.items() if v is not None})

        return TestConfig(
            name=test_name,
            iterations=int(base["iterations"]),
            concurrency=int(base["concurrency"]),
            duration=int(base["duration"]),
            warmup_iterations=int(base["warmup_iterations"]),
            image=str(base.get("image") or "busybox:latest"),
            cri_lifecycle_image=str(base.get("cri_lifecycle_image") or ""),
            cri_host_network=bool(base.get("cri_host_network", True)),
        )

    def get_report_config(self) -> ReportConfig:
        """获取报告配置"""
        report_cfg = self._config.get("report", {})
        return ReportConfig(
            output_dir=report_cfg.get("output_dir", "./results"),
            formats=report_cfg.get("formats", ["console", "json"]),
            include_charts=report_cfg.get("include_charts", True),
            include_raw_data=report_cfg.get("include_raw_data", False)
        )

    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return self._config.get("logging", {
            "level": "INFO",
            "file": "isulad-perf.log"
        })

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, key: str, value: Any):
        """设置配置项"""
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def save(self, file_path: Optional[str] = None):
        """保存配置到文件"""
        save_path = file_path or self.config_file
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'w', encoding='utf-8') as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)
