# WaveLab AI

**用自然语言和可视化编辑，把波形数据整理成科研图。**

WaveLab AI 是面向电气工程、电力电子及其他时序数据分析场景的本地绘图工作台。导入仿真软件、示波器或录波仪导出的 TXT/CSV 数据，选择通道、组织子图、调整样式，即可导出论文和报告所需的 PDF、SVG、PNG。也可以连接 Codex，用自然语言完成绘图修改。

[快速开始](#快速开始) · [绘图教程](docs/getting_started.md) · [Codex 接入](docs/codex_mcp.md) · [示例数据](examples/stage03c1_demo/README.md)

## 主要功能

- **数据导入**：上传 TXT/CSV、粘贴表格文本，支持多通道和重复列名。
- **交互绘图**：多子图、曲线分组与排序、图例、坐标范围、事件标记、局部放大图。
- **科研排版**：单栏/双栏尺寸、中英文标签、物理量与单位设置、矢量图导出。
- **自然语言编辑**：通过 Codex MCP 或 ChatGPT 协作，描述需要修改的图形内容。
- **工程复用**：保存数据和绘图设置，重新打开继续编辑，支持撤销与恢复。

## 快速开始

准备 **Python 3.11+** 和浏览器。手动绘图可直接使用，AI 功能按需配置。

### 下载

点击 **[下载 ZIP](https://github.com/lishihui500/WaveLab-AI/archive/refs/heads/main.zip)** 并解压，或使用 Git：

```bash
git clone https://github.com/lishihui500/WaveLab-AI.git
cd WaveLab-AI
```

在包含 `app.py` 的项目目录打开终端，执行对应系统的命令。首次安装需要联网下载依赖。

### Windows（PowerShell）

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

如果使用 `python` 命令启动 Python，将第一行改为 `python -m venv .venv`。

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

浏览器打开 **[http://127.0.0.1:8501](http://127.0.0.1:8501)**。以后启动时执行最后一行即可；使用期间保持终端运行，结束时按 `Ctrl+C`。

## 画出第一张图

1. 在左侧“导入 TXT / CSV”上传 [`synthetic_arms.csv`](examples/stage03c1_demo/synthetic_arms.csv)，点击“导入上传文件”。
2. 选择目标子图，勾选要绘制的通道并应用。
3. 在右侧调整颜色、线型、图例和坐标范围；通过“添加子图”组织多幅波形。
4. 在“导出论文图”选择 PDF、SVG 或 PNG，点击“导出当前视图”，下载图形文件。
5. 填写工程名称，点击“保存工程”，下次从“已保存工程”继续编辑。

[跟着六桥臂示例完成三幅子图 →](examples/stage03c1_demo/README.md)

## 用自然语言修改图形

连接 Codex 后，打开工程，点击“设为 Codex 编辑目标”，即可提出绘图要求：

> 将六条曲线按 A、B、C 三组排成三幅子图，每组两条曲线。
>
> 把第一幅子图的第二条曲线改为红色虚线，图例放在顶部。
>
> 在 1.49–1.51 s 添加局部放大图，放在右上角。

[配置 Codex MCP →](docs/codex_mcp.md)

也可使用 [ChatGPT 手动协作](docs/manual_dialogue_workflow.md)，或在工作台的“其他方式：ChatGPT / API”中配置模型服务。

## 文档导航

| 想做什么 | 阅读文档 |
|---|---|
| 导入自己的数据，设置单位、事件与局部图 | [绘图与使用指南](docs/getting_started.md) |
| 使用示例数据练习 | [六桥臂绘图教程](examples/stage03c1_demo/README.md) |
| 让 Codex 直接修改图形 | [Codex MCP 接入](docs/codex_mcp.md) |
| 在 ChatGPT 中讨论并应用绘图方案 | [ChatGPT 协作](docs/manual_dialogue_workflow.md) |
| 换电脑、更新软件或排查启动问题 | [工程管理与常见问题](docs/getting_started.md#工程管理) |
| 运行测试、了解代码和协议 | [开发指南](docs/development.md) |

## 项目与许可

WaveLab AI 是 AI 辅助科研绘图课程项目，由作者提出需求、设计绘图流程并核对结果，Codex 辅助软件实现与测试。工作台采用 Python、Streamlit 和 Matplotlib 构建。

代码、技术文档与公开示例采用 [MIT 许可证](LICENSE)。示例数据由正弦公式生成，可用于教学、演示和绘图练习。真实科研数据、个人工程及单独提供的海报、报告按各自授权使用。

欢迎通过 [Issues](https://github.com/lishihui500/WaveLab-AI/issues) 反馈问题或提出建议。请附操作系统、Python 版本、复现步骤和报错信息。
