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

以下测试使用自身构造的输入，可在下载仓库后运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_parser.py tests/test_figure_spec.py tests/test_ai.py tests/test_manual.py tests/test_manual_dialogue.py tests/test_local_bridge.py tests/test_mcp_workflow.py tests/test_mcp_insets.py -q
```

其余历史验收测试与部分 scripts 工具使用 `test/fixtures/`、`reports/` 中的本地资料。运行前查看各脚本输入与输出位置。完整案例资料由维护者单独管理。

## 技术资料

- [绘图架构](architecture.md)
- [MCP 协议与事务](mcp_reference.md)
- [物理量与单位](quantity_presets.md)

带阶段编号的文档保留各阶段设计与实验记录，日常使用以[使用指南](getting_started.md)为入口。提交代码前请阅读根目录 AGENTS.md。
