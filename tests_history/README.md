# 历史验收测试

本目录保留各开发阶段的验收测试与回归记录对应的代码。默认 `python -m pytest -q` 运行 `tests/` 中可独立执行的公开测试。

历史测试可能依赖未随仓库提供的 `test/fixtures/`、`.wavelab/projects/` 或 `reports/`，部分断言对应当时的界面和协议。复现实验时，先核对相应阶段的文档、数据与代码版本，再显式选择测试文件。例如：

```powershell
.\.venv\Scripts\python.exe -m pytest tests_history/test_real_data.py -q
```

公开绘图练习见 [README](../README.md)。
