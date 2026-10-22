# Codex MCP 本地直连工作台

## 安装与启动

在项目目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[mcp,test]'
.\start_workbench.ps1
```

浏览器打开 `http://127.0.0.1:8501`，导入数据或打开已有工程。页面底部显示本次 GUI 会话 ID。保持该浏览器页面连接；暂停或关闭页面后，15 秒内失去心跳的会话拒绝新请求。重开浏览器会获得新会话 ID。

MCP 启动入口（不依赖命令行当前目录，使用本项目已安装环境）：

```powershell
& 'C:\学习\WaveLab_AI\.venv\Scripts\python.exe' -m wavelab.mcp_server
```

该命令使用 stdio 协议，普通用户无需手动运行它；Codex 负责启动。日志输出至 stderr，不向 stdout 打印普通日志。使用 SDK 1.x 接口，测试环境安装版本为 1.30.0；依赖限制为 `>=1.26,<2`，升级到 SDK 2.x 需单独迁移验证。

## Codex 注册

已提供 `.codex/config.toml` 项目级配置。[官方 MCP 文档](https://developers.openai.com/codex/mcp)说明项目级配置仅在受信任项目中生效。2026-10-18 本机没有该项目的信任配置，实际执行 `codex mcp get wavelab --json` 未发现项目级条目。因此本次另通过官方 CLI 注册了用户级 `wavelab`，保留原有 `node_repl` 等配置，没有修改项目的信任级别。

注册命令：

```powershell
codex mcp add wavelab --env 'WAVELAB_RUNTIME_DIR=C:\学习\WaveLab_AI\.wavelab\runtime' -- 'C:\学习\WaveLab_AI\.venv\Scripts\python.exe' -m wavelab.mcp_server
codex mcp get wavelab --json
```

安装位置变更时同步修改命令中的环境路径和项目配置。用户级条目对其他项目也可见，但仅发现此 WaveLab 目录的运行实例；每次操作都必须明确选择会话。

重启 Codex 的 MCP 连接或重新打开 Codex，确认 `wavelab` 工具已加载。当前开发聊天不能用修改配置后的文件，证明其已经热加载新工具。本次用真实 SDK stdio 客户端验证了工具发现、GUI 排序和撤销；重新加载后由 Codex 原生工具完成自然语言调用仍需验收。

## 日常使用

默认是绘图操作模式。例如：“把第三幅子图移动到第一幅。”明确说“工作台开发模式”或要求开发、修复功能时，才修改源码。

1. 用户在已打开工程的页面底部“Codex 本地连接”点击“设为 Codex 编辑目标”。跨同一 runtime 目录的端点只保留最后一次明确选择；可解除或改选。会话失活、工程 epoch 变化、端点重启后需重新绑定。工程名和端口均不作为唯一身份。
2. Codex 每条新指令先调用 `get_edit_target()`，取得唯一目标；未绑定时请用户选择，不枚举后猜测，不依赖浏览器自动化。目标记录只有端点身份、session_id 和 project_epoch，GUI 仍独占可编辑工程。
3. 一次 `get_figure_context(session_id)` 取得当前版本、完整图形配置、通道采样摘要和当前窗口可绘制状态。不重复获取 status。指定 `window_s=[开始秒,结束秒]` 可只读预检绝对时间窗，返回窗口内实际有限样本数；不能用起止时间推断中间连续性。子图可绘制判断复用局部图渲染的 `window_data`，数字轨道保留前一状态的语义。
4. `get_plot_action_schema()` 按协议 hash 复用一次。应用发布版本与协议版本分开；请求只携带协议版本/hash，双方不一致拒绝执行，提示重启 GUI 与 MCP。不要反复获取旧 MCP 进程的 schema。
5. `apply_plot_actions` 一次提交用户原始指令、session_id、expected_project_epoch、expected_revision、expected_fingerprint 及全部 Action。检查结果后一次上下文回读，核对实际属性与 fingerprint。一次批量操作对应一个撤销单元。
6. 用户明确要求保存时，调用 `save_project` 并携带当前四项身份。仅保存已由 GUI 保存过、位于当前工作台 projects 目录的工程；无任意文件名/路径参数。返回 `saved=true`、`saved_revision` 和 `saved_fingerprint` 才可报告已保存；失败返回 `save_failed`，尚未命名或外部路径返回 `save_requires_gui`。不把成功绘图当作已保存。

稳定流程为“目标查询 → 上下文/窗口预检 → 原子提交 → 回读”，4次工具调用；首次另取 schema，明确保存另加1次。绑定和 schema 已在本条指令内确认后，核心修改闭环为3次。多会话仅需一次目标查询，不逐个读取工程。路由缓存以 runtime 目录和 session_id 为键，最多256条、30秒期限；命中时直达，端点失败或会话失效时清除/重新发现。写入连接结果未知时先回读，绝不自动重放。

响应 `diagnostics` 提供统一 request_id、成功状态和毫秒级阶段计时：发现、路由、RPC传输、入队、GUI等待、工程读取、动作准备校验、渲染、提交和响应编码。各阶段可能嵌套，不能相加当作总耗时；未执行阶段不返回数值，不能当作0。Bridge 内存保留最近256条匿名性能记录，不记录波形、凭证、工程内容；RPC总耗时不含 Codex 外部工具调度。没有修改0.5秒队列轮询周期。

“第三幅”表示当前 panels 数组索引 2，不代表 ID 尾号为 3。使用读取到的真实 ID。新建子图时显式指定唯一 ID，后续动作在同一事务中引用该 ID。

支持已有 Executor 的子图新建/删除/移动、曲线添加/移动/删除及样式、双语图例、坐标轴、时间窗口、事件、纸张、语言、撤销/恢复，以及局部放大图创建、修改、删除。保留原有手动 JSON Planner、GUI、保存、导出。不会推断未确认的 ABC、桥臂映射、物理量、单位或故障时刻。

`get_quantity_presets` 返回物理量/单位候选。实际可用 Action 以本次匹配协议的 schema 为准；源属性由 `set_channel_properties` 修改，单位仍需用户明确确认，不转换源样本。详见[物理量与单位预设](quantity_presets.md)。

### 局部放大图

复用 `apply_plot_actions`，先读取当前状态和 `get_plot_action_schema`，再提交以下 Action。无需新增独立状态或改动配置文件。

```json
{
  "action": "create_inset",
  "panel_id": "从当前上下文读取的真实子图ID",
  "inset_id": "zoom_new_unique_id",
  "changes": {
    "xlim_s": [1.49, 1.51],
    "bounds": [0.55, 0.5, 0.4, 0.4],
    "channel_ids": [],
    "show_region": true,
    "show_connectors": true
  }
}
```

- `create_inset`：明确指定全图唯一的新 inset_id；必须提供 xlim_s。父图需要存在可见曲线且该范围含有效样本。
- `update_inset`：用真实 panel_id、inset_id，只在 changes 中传需要修改的字段；其余字段、主图样式和其他局部图保持不变。
- `remove_inset`：只传 action、panel_id、inset_id，不传 changes；错误 ID 或所属子图错误会拒绝。
- `xlim_s` **始终是绝对秒值**。主图显示相对毫秒时，绝对秒 = 显示值 / 1000 + 已知事件原点。原点不明确时先澄清，不猜故障时间；切换坐标显示不会改变已保存的局部窗口。
- `bounds` 为 `[左侧, 底部, 宽度, 高度]`，相对于父图坐标区，四项必须保证局部图完全在父图内部。例如 `[0.05,0.5,0.4,0.4]` 移到左上方。
- `channel_ids=[]` 继承主图当前全部可见曲线；非空数组只能引用该父图已有曲线。局部图颜色、线型、线宽随主图继承，不生成新波形。
- `ylim=null` 恢复局部图自动纵轴；show_region/show_connectors 分别控制范围框与连接线。修改位置、尺寸、范围、曲线选择可以合并在同一次 update_inset。

所有动作仍校验 revision/fingerprint/project_epoch、预览并作为一个事务进入撤销历史。批量新建两幅局部图可分别使用不同 inset_id；任一无效不会留下部分修改。上下文直接包含每幅子图已有 insets，可在修改后回读核对。

更新代码后，应先保存工程，重启已有 WaveLab 进程及 Codex MCP 连接以载入新的 Action；已经运行的进程可能仍缓存旧模块。

`version_conflict`：重新读取并按用户原始意图生成操作。`gui_unresponsive`：尚未开始的请求已经取消，恢复页面连接后重新查询。`connection_lost`：执行结果未知，先读取状态，禁止盲目重试写入。所有工具同步执行，无额外任务状态副本。

## 手动验收

使用新浏览器会话和合成数据，避免修改已有科研工程：

```text
Domain,u,u
0,1,2
0.1,2,1
0.2,1,3
```

导入后从页面读取真实会话 ID，以下 `<session>` 替换为它：

```powershell
.\.venv\Scripts\python.exe scripts\verify_mcp_stdio.py --session <session> --mode setup --output reports\stage_mcp\setup.json
.\.venv\Scripts\python.exe scripts\verify_mcp_stdio.py --session <session> --mode move --output reports\stage_mcp\move.json
```

setup 仅适用于刚导入、仅有一幅子图的合成测试项目，会通过 MCP 创建另外两幅子图及测试曲线。观察排序卡片和图形顺序成为 `mcp_demo_3, panel_1, mcp_demo_2`，点击 GUI“撤销”一次后，应恢复 `panel_1, mcp_demo_2, mcp_demo_3`。

```powershell
.\.venv\Scripts\python.exe scripts\verify_mcp_stdio.py --session <session> --output reports\stage_mcp\gui_undo.json
.\.venv\Scripts\python.exe -m pytest -q --junitxml=reports/stage_mcp/pytest.xml
```

撤销后的 fingerprint 应与 setup 后完全相同，但 revision 递增。继续验证：旧 revision 写入被拒绝；错误 ID 不修改配置；同版本并发写入仅首个成功；失败批量不产生部分修改；保存/重开保持配置与样本；关闭 MCP 客户端不影响 GUI；关闭目标浏览器、等待心跳失效后拒绝写入；两个浏览器会话必须明确选择。

重新加载 Codex 工具后，直接输入“把第三幅子图移动到第一幅”，再检查它确实调用了 `wavelab` 工具。这是原生 Codex 接入的最后验收，SDK 客户端测试不能替代它。

## 进程与安全边界

GUI 持有唯一 Workbench；HTTP 后台线程只写有界队列，Streamlit 的 `run_every=0.5` fragment 在 GUI 会话线程处理请求。轮询位于控件注册之后，避免外部刷新打断按钮状态更新。断连会话在 15 秒后拒绝请求；排队超过 30 秒且未执行的请求取消，不会延迟写入。已开始的请求返回实际结果，客户端连接中断时需重新查询。

项目配置 `runner.fastReruns=false`，使同一会话等待当前脚本到达让出点后处理 GUI 重跑，避免事务渲染期间启动替代脚本并同时修改 Workbench。此设置需重启已有 Streamlit 进程生效。

HTTP 仅绑定 127.0.0.1 随机端口，所有读取和写入都要求每进程随机令牌；拒绝带 Origin 的网页请求，限制请求体大小。令牌保存在忽略版本管理的 `.wavelab/runtime`，Windows 目录 ACL 限于当前账户继承，POSIX 为 0700。令牌不会发给模型或日志。进程正常结束删除自身描述文件；异常退出的描述文件通过实际连接探测跳过，不按文件内容伪造在线状态。

MCP 不提供文件访问、Shell、Python 执行、导入路径或模型 API。元数据不包含完整数组、源文件路径和确认来源文本。数据不经 MCP 发送完整波形；源 TXT 不被修改。没有新增 API Key、模型调用或云服务器。已有 GUI API Provider 仍保留，其原有费用和授权流程未被本模块调用。
