# WaveLab AI

本地科研波形绘图工作台。导入仿真软件/示波器/录波仪的波形数据（如PSCAD 图窗导出的 TXT/CSV），用统一绘图配置完成手动编辑、Codex MCP 操作和 Matplotlib 科研图导出。

## 功能

- 保留原始采样、重复表头和通道列序，以数据集 ID + 原始列索引识别通道。
- 多子图、曲线样式、图例、事件标记、绝对/相对时间轴及局部放大图。
- 中英文图形标签、单位显示换算、PDF/PNG/SVG 导出。
- 本地工程保存与重开、撤销与恢复；不配置模型 API Key 也可使用。
- Codex 显式编辑目标、白名单原子操作、版本校验、采样窗口预检和协议一致性检查。
- 另提供 ChatGPT 手动 JSON 协作与可选 OpenAI 兼容 API；API 仅在用户确认并点击生成时调用。

## 安装与启动

需要 Python 3.11 或更高版本；本机测试环境为 Windows + Python 3.14，其他环境尚未完整验收。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[mcp,test]"
.\start_workbench.ps1
```

打开 <http://127.0.0.1:8501>。也可直接运行：

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

代码更新后请保存工程、重启现有服务，再重新打开工程。默认不启用文件热重载。

## 使用

1. 从左侧导入或粘贴数据，或打开已保存工程。
2. 选择通道、确认实际单位与物理映射，再设置子图和样式。
3. 在上方“AI 科研绘图助手”点击“设为 Codex 编辑目标”，随后在 Codex 中输入绘图要求。
4. 修改通过原子事务提交并回读；需要保存时明确提出，或使用 GUI 保存按钮。
5. 在画布下方导出论文图。迁移工程时复制整个工程目录及其 data 子目录。

MCP stdio 启动命令：

```powershell
.\.venv\Scripts\python.exe -m wavelab.mcp_server
```

在 Codex 的 MCP 配置中使用上述解释器的实际绝对路径，参数为 `-m wavelab.mcp_server`。完整流程、错误处理及保存边界见 [Codex MCP 指南](docs/codex_mcp.md)。

## 公开示例与测试

[合成六桥臂示例](examples/stage03c1_demo/README.md)可用于公开演示。公开仓库不包含真实科研仿真数据、个人绘图工程、密钥、运行日志或历史课程交付副本。

可独立运行的快速回归：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_parser.py tests/test_figure_spec.py tests/test_ai.py tests/test_manual.py tests/test_manual_dialogue.py tests/test_local_bridge.py tests/test_mcp_workflow.py tests/test_mcp_insets.py -q
```

完整历史测试包含依赖私有 `test/fixtures/` 和本地 `reports/` 的验收项，公开仓库未附带这些输入，直接运行全部测试会遇到缺失文件。不要用合成数据冒充真实验收样本。部分 scripts/ 工具同样依赖本地历史资料，使用前查看其输入要求。

## 代码结构

| 目录/文件 | 用途 |
|---|---|
| `app.py` | Streamlit 工作台入口 |
| `src/wavelab/` | 数据模型、解析、绘图、工程服务、Action Executor 与 MCP |
| `tests/` | 单元、事务和 GUI 回归测试 |
| `examples/` | 可公开的合成案例 |
| `scripts/` | 验证与性能测量工具 |
| `docs/` | 功能与协议说明；带阶段编号的文档是历史设计记录 |

默认工作数据保存在 `.wavelab/`，不纳入 Git。`.streamlit/secrets.example.toml` 为可选 API 配置模板；实际 secrets.toml 不得提交。AI 仅修改受校验绘图配置，不执行任意生成代码，也不隐式平滑、插值或重采样。

更多说明：[物理量与单位](docs/quantity_presets.md) · [手动协作](docs/manual_dialogue_workflow.md) · [绘图架构](docs/architecture.md)。
