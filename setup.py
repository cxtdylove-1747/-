"""
iSulad Performance Testing Framework Setup
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="isulad-perf-framework",
    version="0.1.0",
    author="Competition Team",
    author_email="",
    description="Performance testing framework for iSulad container engine",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://gitee.com/openeuler/iSulad",
    # 同时包含顶层包（core/engines/cli/...）与兼容包（isulad_perf）
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Mulan Permissive Software License v2 (MulanPSL-2.0)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "isulad-perf=isulad_perf.cli.main:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
