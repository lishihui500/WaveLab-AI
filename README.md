# WaveLab AI · 科研波形绘图工作台

将 PSCAD 等软件导出的 TXT/CSV 波形整理为可编辑、可复现的科研图，支持手动编辑、AI 辅助操作与 PDF/SVG/PNG 导出，保留原始采样。

**第一次体验只需要 Python、浏览器和本仓库，无需安装 PSCAD、MATLAB、Codex，也无需模型 API Key。** 当前提供源码运行方式，尚无 Windows 安装包或独立可执行程序。

[下载与安装](#下载与安装) · [第一张图](#完成第一张图) · [迁移与排错](docs/getting_started.md) · [材料来源与公开范围](#材料来源与公开范围)

## 可以做什么

- 导入 TXT/CSV 或粘贴数据，保留重复表头，以数据集 ID 和原始列索引区分通道。
- 多子图、曲线样式、图例、坐标范围、事件标记、相对时间轴与局部放大。
- 中英文标签、物理量和显示单位设置，Matplotlib 科研图导出。
- 完整工程保存与重开，撤销与恢复。
- 可选 Codex MCP、ChatGPT 手动 JSON 协作和 OpenAI 兼容 API；AI 下发受校验的结构化操作。

适合电气工程与电力电子时域波形整理。当前导入对象为数值文本，不直接读取 PSCAD 工程、`.psout`、Simulink 模型或仪器专有二进制文件。

## 下载与安装

### 1. 获取代码

无需 Git：点击仓库页 **Code → Download ZIP**，解压到自己可写的目录，如 `D:\WaveLab-AI`。进入包含 `app.py` 和 `pyproject.toml` 的那层文件夹，打开终端。

已安装 Git 的读者也可执行：

```text
git clone https://github.com/lishihui500/WaveLab-AI.git
cd WaveLab-AI
```

### 2. 安装环境并启动

需要 **Python 3.11 或更高版本**，首次安装需联网。Windows 为主要验证平台；macOS/Linux 提供对应命令，尚未完成实机验收。依赖由 `pyproject.toml` 声明，pip 自动安装 NumPy、Pydantic、Matplotlib 和 Streamlit。基础绘图无需 LaTeX。

**Windows PowerShell**，无需激活虚拟环境：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

若没有 `py`，确认 `python --version` 满足要求后，第一行改为 `python -m venv .venv`。

**macOS / Linux**：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

保持终端运行，浏览器打开 [本地工作台](http://127.0.0.1:8501)。日常启动只需执行最后一行；Windows 也可运行 `start_workbench.ps1`。退出前保存工程，再在终端按 `Ctrl+C`。

## 完成第一张图

1. 在左侧“导入 TXT / CSV”选择 `examples/stage03c1_demo/synthetic_arms.csv`，点击“导入上传文件”。这是 **401 个时间点、6 个通道的合成示例**。
2. 按原始列序识别通道。本示例约定为 A上、A下、B上、B下、C上、C下，单位 kV；通过界面确认映射并设置展示名称。这些约定仅用于此示例。
3. 在子图设置中选择通道；点击“添加子图”，将六条曲线分为三组，每组两条。
4. 设置时间范围为 `1.3–1.7 s`，调整颜色、线型、图例及坐标标题，查看“画布与导出”。
5. 输入新工程名称，点击“保存工程”。在“导出论文图”选择格式，点击“导出当前视图”，下载图形 ZIP。
6. 重启工作台，从“已保存工程”打开工程，核对曲线与设置。

完整练习见[公开示例说明](examples/stage03c1_demo/README.md)。合成曲线仅演示软件操作，不用于证明真实故障机理或系统性能。

### 导入自己的数据

首行是表头，首列 `Domain` 为时间，单位秒；后续列为波形值。例如：

```csv
Domain,signal,signal
0.000,1.0,2.0
0.001,1.2,1.8
0.002,1.1,1.9
```

允许重复表头，时间应严格递增。全空尾行会被忽略并提示；部分缺失、非数值及异常时间需要核对。请确认单位、相序、桥臂映射和事件时刻。程序不隐式平滑、插值或重采样。

## 选择 AI 使用方式

| 方式 | 需要准备 | 使用入口 |
|---|---|---|
| 手动编辑 | 基础安装，无账号或 Key 要求 | 工作台属性面板 |
| ChatGPT 手动协作 | 可使用的 ChatGPT，按界面传递快照和最终 JSON | [协作指南](docs/manual_dialogue_workflow.md) |
| Codex MCP | Codex、额外 mcp 依赖与本机路径配置 | [MCP 指南](docs/codex_mcp.md) |
| OpenAI 兼容 API | 自备服务、Key 和模型配置，费用按服务方规则计算 | `.streamlit/secrets.example.toml` 与助手界面 |

基础手动功能不需要 AI 服务。使用 MCP 前额外安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[mcp]"
```

按 MCP 指南配置**本机实际解释器及 runtime 路径**，不要照抄作者电脑路径。打开工程后，在“AI 科研绘图助手”点击“设为 Codex 编辑目标”，再输入要求，例如“将第二条曲线改成红色虚线，其他设置保持不变”。保存需另行明确提出或点击 GUI 保存按钮。

## 保存、迁移与升级

- 默认本地工作目录为仓库下 `.wavelab/`；工程在 `.wavelab/projects/<工程名>/`。
- **导出图片和 FigureSpec JSON 不等同于完整工程。** 跨电脑继续编辑时，复制整个工程目录，包含 `project.json` 和 `data/`，放到目标仓库的 `.wavelab/projects/` 下，从 GUI 打开。
- 新电脑重新创建 `.venv` 并安装依赖，不复制旧电脑虚拟环境和绝对路径配置。
- 更新前保存并备份工程。更新代码后重新执行安装命令，重启工作台及 MCP，再打开工程；默认关闭文件热重载。

详细步骤见[首次使用、迁移与排错](docs/getting_started.md)。

## 材料来源与公开范围

本项目是 AI 辅助科研绘图的课程成果，面向电气工程和电力电子时域数据整理。作者负责需求、物理语义确认、真实案例核对与成果审核，Codex 辅助实现、修改与测试软件。AI 操作受 Action Executor 白名单、事务和版本校验约束，不执行任意模型生成代码。

| 材料 | 来源 | 当前公开范围 |
|---|---|---|
| 工作台源码、测试与技术文档 | 本项目开发成果，第三方组件见 `pyproject.toml` | 随仓库公开，供课程浏览、交流和绘图实践 |
| `synthetic_arms.csv` | 仓库脚本按正弦公式生成，详见示例说明 | 可公开演示，须标注合成数据 |
| 真实 PSCAD 仿真数据、个人工程与验收记录 | 作者科研工作 | 不随公开仓库提供，未公开成果须另行取得授权 |
| 海报、报告、课程提交压缩包 | 单独维护的课程材料 | 当前仓库不附带，公开展示前单独审核与脱敏 |
| API Key、配置凭据、运行日志 | 使用者本机 | 不公开，不应提交到 GitHub |

公开代码不自动授予私有数据使用权。**当前仓库尚未添加开源许可证**；再分发、修改后发布或其他授权请先联系仓库作者。第三方软件遵循各自许可证。分享工程或截图前，核对数据来源、姓名/学号、本机路径、研究参数和凭据；`.gitignore` 不能替代公开内容审核。

## 测试与开发资料

安装测试和 MCP 依赖后，可运行不需要私有数据的快速回归：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[mcp,test]"
.\.venv\Scripts\python.exe -m pytest tests/test_parser.py tests/test_figure_spec.py tests/test_ai.py tests/test_manual.py tests/test_manual_dialogue.py tests/test_local_bridge.py tests/test_mcp_workflow.py tests/test_mcp_insets.py -q
```

完整历史测试和部分 `scripts/` 工具依赖未公开的 `test/fixtures/`、`reports/`，直接运行全部测试会遇到缺失文件。公开示例不能替代真实样本验收。依赖目前使用版本范围，尚无锁定全部传递依赖的跨平台环境文件。

| 路径 | 用途 |
|---|---|
| `app.py` | Streamlit 工作台入口 |
| `src/wavelab/` | 解析、模型、渲染、工程服务、Action Executor 与 MCP |
| `examples/` | 公开合成示例与练习 |
| `tests/` | 单元、事务及 GUI 回归测试 |
| `docs/` | 使用与协议说明；阶段编号文档为历史记录 |
| `scripts/` | 验收与历史交付工具，执行前核对输入和写入位置 |

更多资料：[物理量与单位](docs/quantity_presets.md) · [绘图架构](docs/architecture.md)。反馈问题请在 [Issues](https://github.com/lishihui500/WaveLab-AI/issues) 提供操作系统、Python 版本、操作步骤和脱敏报错，优先用公开示例复现。
