# Dong 微电网能源管理系统 v1.4

Dong 是面向程序设计课程大作业的 Windows 桌面应用，使用 Python、PySide6、Matplotlib、NumPy 和 Pandas 实现微电网典型日调度、光伏不确定性分析、仿真回放与结果导出。v1.4 在日前计划基础上加入 EWMA 滚动预测、4 小时滚动动态规划和主网负载状态判断。

> “实时仿真”页面回放的是模型计算结果，不接入真实硬件，也不表示在线监控数据。

## 快速启动

便携版无需安装 Python，保持整个文件夹完整并双击：

```text
dist\DongMicrogridEMS\DongMicrogridEMS.exe
```

源码版首次运行：

1. 安装 Windows x64 Python 3.11 或更高版本。
2. 双击 `setup.bat` 创建本地 `.venv` 并安装依赖。
3. 双击 `run.bat` 启动。

也可在 PowerShell 中运行：

```powershell
.\.venv\Scripts\python.exe main.py
```

完整图文说明、录屏脚本、数据格式与故障排查见 [USER_MANUAL.md](USER_MANUAL.md)。

## v1.4 功能

- 96 个 15 分钟时段的确定性动态规划调度。
- 光伏 P50、置信区间、P 下界风险感知计划和实时偏差补偿。
- 无储能基础方案，用于计算节省费用、购电量和碳排放变化。
- 三种典型日、CSV 导入、组件参数编辑和逐时约束检查。
- 50Hertz 德国区域光伏 2025 年度数据：365 个日期可选，自动处理 92/97 点夏令时日期。
- 透明日前预测：使用过去 14 天同一时刻中位数；软件明确标注这不是官方预测值。
- 页面淡入、KPI 更新脉冲和按钮点击反馈动画，不改变布局尺寸。
- 八个页面：运行总览、实时仿真、滚动调度中心、微电网拓扑、策略对比、场景实验室、96 时段明细、运行报告。
- 三种可比较策略：确定性 P50、风险感知 P 下界、滚动预测调度（4h MPC）。
- 每小时重规划：使用过去已发生的光伏预测误差更新 EWMA 偏差，并修正未来 4 小时预测。
- 电网状态判断：正常、电网紧张、高价削峰、保供告警，并记录重优化原因。
- Monte Carlo 相关光伏误差分析，默认 200 个场景和随机种子 2026。
- 储能或光伏容量敏感性分析，默认 7 个等距方案点。
- `.dong` 项目新建、打开、保存、未保存提示和版本校验。
- 报告包导出：Markdown、调度 CSV、指标 JSON、实验 CSV 与 PNG 图表。
- 源码与文件夹版 Windows x64 EXE；支持自动页面截图冒烟测试。

## 工程结构

```text
Dong_v1.4/
├─ main.py
├─ microgrid/
│  ├─ models.py             # 组件与场景模型
│  ├─ data.py               # 内置场景、通用 CSV 与 50Hertz 年度数据
│  ├─ scheduler.py          # 调度计划、执行和基础方案
│  ├─ analysis.py           # Monte Carlo 与容量敏感性
│  ├─ project.py            # .dong 项目格式
│  ├─ reporting.py          # 报告包生成
│  └─ ui/                   # 七页桌面界面与后台工作线程
├─ sample_data/             # 示例 CSV 与 .dong 项目
├─ tests/                   # 核心和 UI 行为测试
├─ docs/                    # 设计文档与最终截图
├─ USER_MANUAL.md           # 完整使用说明书
└─ CHANGELOG.md             # 版本变更记录
```

## 开发与验证

运行全部测试：

```powershell
$env:PYTHONNOUSERSITE='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

生成指定页面截图：

```powershell
.\.venv\Scripts\python.exe main.py --screenshot docs\screenshots\replay.png --screenshot-tab replay --window-size 1500x920
```

`--screenshot-tab` 支持 `overview`、`replay`、`rolling`、`topology`、`comparison`、`lab`、`details` 和 `report`。

构建文件夹版 EXE：

```text
双击 build_exe.bat
```

构建结果位于 `dist\DongMicrogridEMS\`。必须整体分发该目录，不能只复制单个 EXE，因为 Qt 和 Matplotlib 运行库位于 `_internal`。

## 模型边界

v1.4 面向课程演示，不包含真实硬件通讯、多日调度、SQLite、柴油机整数启停约束或真实在线 MPC。滚动调度中心是离线回放：它按时间顺序只读取已经发生的光伏数据，不读取未来实测值。50Hertz 文件是区域光伏功率估算曲线，日前预测由历史同刻中位数构造，不应在答辩时描述为官方预测准确率评估。
