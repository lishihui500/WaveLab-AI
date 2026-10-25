# 开发指南

## 代码结构

| 路径 | 用途 |
|---|---|
| `app.py` | Streamlit 工作台入口 |
| `src/wavelab/ingest/` | TXT/CSV 解析 |
| `src/wavelab/domain/` | 数据集、通道与 FigureSpec 模型 |
| `src/wavelab/render/` | Matplotlib 渲染与导出 |
| `src/wavelab/commands/` | 结构化绘图操作 |
| `src/wavelab/ai/` | AI 助手与手动协作 |
| `tests/` | 单元与集成测试 |
| `examples/` | 公开示例 |

## 安装开发依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[mcp,test]"
```

## 运行公开回归测试

默认测试使用随仓库提供的公开输入，覆盖解析、绘图配置、AI 方案、事务、局部图和编辑目标恢复。在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

历史验收测试保存在 `tests_history/`，相关真实样本和实验记录由维护者单独管理。历史测试的运行方法见 [历史测试说明](../tests_history/README.md)。

## 技术资料

- [绘图架构](architecture.md)
- [MCP 协议与事务](mcp_reference.md)
- [物理量与单位](quantity_presets.md)

带阶段编号的文档保留各阶段设计与实验记录，日常使用以[使用指南](getting_started.md)为入口。提交代码前请阅读根目录 AGENTS.md。
