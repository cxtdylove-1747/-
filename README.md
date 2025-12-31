# iSulad Performance Testing Framework

为iSulad容器引擎设计的性能测试框架，支持CRI和Client接口类型的性能测试，以及多种容器引擎的对比测试。

## 特性

- **多接口支持**: 支持CRI和Client两种接口类型的性能测试
- **多引擎对比**: 支持iSulad、Docker、CRI-O等容器引擎的性能对比
- **模块化设计**: 基于微服务设计思想，具有高可扩展性
- **完整测试流程**: 包含测试执行、数据处理和结果展示
- **用户友好**: 提供丰富的CLI界面和直观的结果展示

## 架构

```
isulad-perf-framework/
├── core/                 # 核心模块
│   ├── config.py        # 配置管理
│   ├── logger.py        # 日志管理
│   └── exceptions.py    # 异常处理
├── engines/              # 容器引擎适配器
│   ├── base.py          # 基础引擎接口
│   ├── isulad.py        # iSulad适配器
│   ├── docker.py        # Docker适配器
│   └── crio.py          # CRI-O适配器
├── executor/             # 测试执行器
│   ├── base.py          # 基础执行器
│   ├── cri_executor.py  # CRI执行器
│   └── client_executor.py # Client执行器
├── processor/            # 数据处理器
│   ├── base.py          # 基础处理器
│   ├── analyzer.py      # 数据分析器
│   └── statistics.py    # 统计计算器
├── reporter/             # 结果展示器
│   ├── base.py          # 基础展示器
│   ├── console.py       # 控制台展示
│   └── html.py          # HTML报告
├── cli/                  # 命令行接口
│   └── main.py          # 主入口
├── tests/                # 测试用例
│   ├── cri_tests/       # CRI测试
│   └── client_tests/    # Client测试
├── config/               # 配置文件
│   └── default.yaml     # 默认配置
└── utils/                # 工具函数
    ├── helpers.py       # 辅助函数
    └── validators.py    # 验证器
```

## 安装

```bash
# 克隆项目
git clone <repository-url>
cd isulad-perf-framework

# 安装依赖
pip install -r requirements.txt

# 安装框架
pip install -e .
```

## 使用

### 基本用法

```bash
# 查看帮助
isulad-perf --help

# 执行CRI性能测试
isulad-perf run cri --engine isulad --test create-container

# 执行Client性能测试
isulad-perf run client --engine isulad --test pull-image

# 引擎对比测试
isulad-perf compare --engines isulad,docker --test create-container

# 生成报告
isulad-perf report --input results.json --output report.html
```

### 配置

框架使用YAML配置文件，可以通过以下方式自定义：

- 全局配置: `~/.isulad-perf/config.yaml`
- 项目配置: `./config/default.yaml`

## 测试类型

### CRI测试
- 容器创建性能
- 容器启动性能
- 容器删除性能
- 镜像拉取性能
- 网络性能
- 存储性能

### Client测试
- API响应时间
- 并发处理能力
- 内存使用情况
- CPU使用情况

## 扩展框架

框架采用模块化设计，易于扩展：

1. **添加新引擎**: 继承`engines/base.py`中的`BaseEngine`
2. **添加新测试**: 在`tests/`目录下添加测试用例
3. **自定义处理器**: 继承`processor/base.py`中的`BaseProcessor`
4. **自定义展示器**: 继承`reporter/base.py`中的`BaseReporter`

## 许可证

MulanPSL v2

## 贡献

欢迎提交Issue和Pull Request！

## 参考

- [iSulad](https://gitee.com/openeuler/iSulad)
- [CRI Tools](https://github.com/kubernetes-sigs/cri-tools)
