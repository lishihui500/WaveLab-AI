# 首次使用、跨电脑迁移与排错

安装入口见[README](../README.md#下载与安装)。先用合成 CSV 完成“导入 → 修改 → 保存 → 导出 → 重开”，再接入科研数据与 AI。

## 环境检查

在含 `app.py` 的仓库根目录执行。macOS/Linux 将下面解释器替换为 `.venv/bin/python`。

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m wavelab.cli examples/stage03c1_demo/synthetic_arms.csv
```

最后一条只读检查示例，应报告 401 行、6 个通道，重复表头保持独立原始列；不会修改源文件。

## 迁移完整工程

1. 旧电脑在 GUI 保存工程并确认成功，退出工作台。
2. 复制 `.wavelab/projects/<工程名>/` 整个目录，包括 `project.json` 和全部 `data/`。
3. 新电脑下载源码、建立新虚拟环境、安装依赖，启动工作台一次后退出。
4. 把工程放入新仓库 `.wavelab/projects/`；同名目录先备份，避免覆盖。
5. 启动后从“已保存工程”打开，核对通道数量、单位、映射、时间范围、局部图和导出结果。

MCP 配置使用新电脑路径并重新绑定编辑目标。不要迁移旧 runtime、会话标识或密钥。普通 GUI 使用本仓库自己的 `.wavelab`；改变端口只改变监听位置，不能据此认定数据目录已隔离。

## 更新已有安装

先保存、备份工程，关闭工作台。Git 安装且无本地代码修改时执行 `git pull --ff-only`；有修改时先处理差异。重新运行原来的 pip 安装命令，再启动。ZIP 用户可解压到新目录、创建新环境并迁移工程。

浏览器刷新不会重新载入全部后台模块；更新后需重启 Streamlit，使用 MCP 时也重启连接。

## 常见问题

| 现象 | 处理方法 |
|---|---|
| 找不到 py 或 python | 安装 Python 3.11+，重开终端，检查 `py -3 --version` 或 `python --version` |
| Linux 缺少 venv | 按发行版安装与当前 Python 匹配的 venv 组件，再创建环境 |
| PowerShell 禁止运行 ps1 | 直接执行 README 中的虚拟环境 Python 启动命令，无需激活脚本 |
| 找不到 app.py | 进入含 app.py 和 pyproject.toml 的仓库根目录 |
| No module named wavelab / streamlit | 用同一虚拟环境解释器安装与启动，重新执行 `-m pip install -e .` |
| pip 下载失败或无匹配版本 | 检查 Python 版本、网络/代理和软件源，保留完整报错，不任意降级依赖 |
| 8501 端口占用 | 关闭自己不用的服务，或改用 `--server.port 8502`，浏览器访问对应端口 |
| 网页打不开 | 保持终端运行，检查报错，手动打开终端显示的本地地址 |
| 中文方框或字体警告 | 系统安装可用中文字体，重启工作台并重新导出检查；不同电脑字体会影响排版 |
| 只有图片，无法继续编辑 | 图片下载与保存工程分开；迁移完整工程及 data 目录 |
| MCP 拒绝事务或找不到工作台 | 核对本机路径，重启连接并绑定目标；版本冲突先重读，见 MCP 指南 |
| 全部 pytest 缺少样本 | 公开仓库不含私有输入，先运行 README 列出的公开快速回归 |

默认监听 `127.0.0.1`，供本机浏览器使用。多名同学可分别安装实践，本文未配置互联网服务。
