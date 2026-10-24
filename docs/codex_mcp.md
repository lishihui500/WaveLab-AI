# 用 Codex 操作工作台

连接后，在 Codex 中描述绘图要求，工作台会直接更新当前工程。先按[首页](../README.md#快速开始)完成基础安装。

## 1. 安装 MCP 依赖

在项目目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[mcp]"
```

macOS/Linux 使用 `.venv/bin/python`。

## 2. 注册到 Codex

已安装 Codex CLI 的 Windows 用户，可在项目根目录运行以下 PowerShell 命令。路径会根据当前目录自动生成：

```powershell
$wavelabRoot = (Get-Location).Path
$wavelabPython = Join-Path $wavelabRoot '.venv\Scripts\python.exe'
$wavelabRuntime = Join-Path $wavelabRoot '.wavelab\runtime'
codex mcp add wavelab --env "WAVELAB_RUNTIME_DIR=$wavelabRuntime" -- $wavelabPython -m wavelab.mcp_server
codex mcp get wavelab
```

macOS/Linux 在项目根目录执行：

```bash
codex mcp add wavelab --env "WAVELAB_RUNTIME_DIR=$PWD/.wavelab/runtime" -- "$PWD/.venv/bin/python" -m wavelab.mcp_server
codex mcp get wavelab
```

也可以在 Codex 的 MCP 配置中添加本地 stdio 服务：

| 配置项 | 内容 |
|---|---|
| 名称 | wavelab |
| 命令 | 本项目虚拟环境 Python 的绝对路径 |
| 参数 | `-m wavelab.mcp_server` |
| 环境变量 | `WAVELAB_RUNTIME_DIR`，值为本项目 `.wavelab/runtime` 的绝对路径 |

配置完成后，重新连接 MCP 或重启 Codex。配置方式见 [OpenAI 官方 MCP 文档](https://developers.openai.com/codex/mcp)。

## 3. 选择要编辑的工程

启动工作台并打开工程，在“AI 科研绘图助手”点击 **“设为 Codex 编辑目标”**。保持该浏览器页面打开，然后回到 Codex 输入要求。

需要跨页面重连和工作台重启保留选择时，先在 GUI 保存工程，勾选 **“保持为 Codex 编辑目标”**，再点击 **“设为 Codex 编辑目标”**。同一工程恢复连接后自动更新会话身份；普通绑定也可在同一会话短暂离线后恢复。

心跳超时只标记目标离线，离线期间拒绝请求。持久授权只适用于同一规范路径、同一数据集 ID 和原始数据哈希；复制到其他位置、改变数据来源或切换工程，需要重新明确选择。“解除 Codex 编辑目标”立即删除授权。另一个仍在运行的工作台不会被自动抢占。

“保持为 Codex 编辑目标”保存的是工程授权。页面短暂离线时，授权仍保留；恢复页面连接后才能继续执行绘图操作。

## 4. 开始绘图

可以直接使用以下指令，也可以替换成自己的通道名称和时间范围：

> 将第一幅子图的第二条曲线改为红色虚线，其他设置保持不变。
>
> 把第三幅子图移到第一幅，所有子图共享时间轴。
>
> 在第一幅子图添加 1.49–1.51 s 的局部放大图，放在右上角。
>
> 保存当前工程。

首次保存时，在工作台填写工程名称并点击“保存工程”。后续可直接要求 Codex 保存；图形文件通过工作台“导出论文图”下载。

## 连接排查

| 提示 | 操作 |
|---|---|
| 未选择编辑目标 | 在目标工程点击“设为 Codex 编辑目标” |
| 编辑目标离线（target_offline） | 恢复已选择的页面连接；持久目标需重新打开同一工程，无需再次绑定 |
| 编辑目标已变化（target_changed） | 重新查询编辑目标和当前工程状态，再按原意生成操作 |
| 找不到工作台 | 检查 GUI 是否运行、页面是否打开、runtime 路径是否一致 |
| 工程版本冲突 | 让 Codex 重新读取当前工程，再按原要求修改 |
| 协议不一致 | 重启工作台与 MCP 连接，再重新选择目标 |
| 工程尚未命名 | 在 GUI 首次保存工程，再继续使用 Codex 保存 |

工具参数、事务和局部图 Action 见 [MCP 开发参考](mcp_reference.md)。
