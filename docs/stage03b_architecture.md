# 阶段 3B 运行时 AI 绘图

## 数据流与权责

Streamlit `ai/ui.py` → `Assistant.propose` → `LLMProvider.generate_actions` → `Plan/Action` → `commands.prepare` → 临时 FigureSpec 校验/试绘 → 用户确认 → `apply_proposal` → `Workbench.commit` → revision/Undo/Redo → 现有渲染与 GUI 控件。GUI、AI 只有一份 FigureSpec；没有第二份有效编辑状态。临时 candidate 不进入保存或导出。

Provider 使用标准库 HTTPS Chat Completions REST，适配 OpenAI 兼容服务，无需新增 SDK。协议依据 [官方结构化输出文档](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)。默认 `json_object` 只保证 JSON 格式，必须继续本地校验；可选 `json_schema` 因动态 partial patch 使用 `strict=false`，不宣称服务端严格约束。兼容服务不支持 response_format 时明确报错，不静默改成任意文本执行。

模型只生成白名单操作：query_context、set_page/languages/time_axis/legend、create/update/remove_panel、add/update/remove/move_series、upsert/remove_event、undo/redo。channel_id/panel_id 是目标身份；changes 为局部 patch。未知操作、目标字段或可执行代码字段拒绝。字段先严格类型验证，候选完整 Pydantic 验证后检查引用、单位、映射、有限范围、同轴单位及共享轴约束。

模型读取全部当前可用通道元数据，可通过 confirmed physical_role 选择 ID；无需新建搜索后端。AI 不修改 datasets、单位、映射、回退单语言字段。双语 patch 合并 zh/en 字段，另一语言不被清空。普通论文宽度操作保留语言；语言操作复用现有默认字体行为，保留自定义字体。专业翻译作为候选双语文本展示，由用户检查确认，未知物理角色标签被拒绝。

新增曲线继承通道确认单位/角色/来源；移动保留整个 SeriesSpec。新增子图追加到纵向列表，已有子图可复用或移除。单个计划最多100个操作，一次成功提交只增加一个撤销记录。冲突的同目标字段编辑拒绝。删除子图时同步删除对应事件引用；不能删除唯一子图。undo/redo 必须独立操作，且不允许借撤销恢复改变数据清单。

## 确定性安全与状态一致性

方案保留 revision 和 FigureSpec 指纹；生成前、生成后、试绘后、应用前均检查当前状态。prepare 在副本上执行所有步骤、核对矩阵 SHA-256、渲染 PNG，失败不提交。apply 重建命令结果并比对 candidate 与差异，重新校验和试绘，成功后才 commit。模型答复“成功”不会影响程序状态。旧方案在手动修改、撤销、打开工程后失效；新请求取最新配置。

结构化事件时刻必须等于现有确认事件，或与用户原话 evidence_quote 中明确给出的秒值一致。未给事件时刻时模型应返回 clarification；试图编造时刻会被执行层拒绝。该证据检查仅用于事件参数授权，不用于用关键词模拟模型理解。未实现波形自动故障识别。

时间 mode/unit/原点变化且没有新 xlim 时，已有窗口通过原始秒坐标换算，保证保留物理区间。显式新 xlim 使用显示单位。事件 time_s 始终原始秒值，波形数组不变。改变时间后已有自定义文字需要用户检查单位表述；不静默改写专业标签。

模型输出无效 JSON/命令时可传结构化错误重提方案，默认最多额外一次，接口允许0–2次。HTTP认证错误、限流、超时不自动重试。显示 HTTP 状态及安全错误代码，不显示远端响应体、URL凭据或密钥。最多60秒单次超时，未增加任意工具执行、文件读写或网络调用工具权限。

## 配置、同意与隐私

复制 `.streamlit/secrets.example.toml` 为 `.streamlit/secrets.toml`，或启动终端配置 `OPENAI_API_KEY`、`WAVELAB_AI_MODEL`、`WAVELAB_AI_BASE_URL`。服务根地址通常以 `/v1` 结尾，模型名称自行填写。远程只允许 HTTPS，本机兼容服务允许 HTTP。拒绝带用户密码、query 或 fragment 的地址；拒绝 HTTP 重定向以防凭据转发。GUI 超时范围1–60秒。

只有启用 AI、检查上下文、勾选当前服务/模型/数据集范围的外传及费用同意，再点击生成时才调用。换服务、模型、数据集或通道元数据重置同意。仅发送 ID、组和显示名称、源列序号、确认角色/单位、图形配置，以及最近六轮用户请求/状态摘要。省略源路径、文件名、工程名、哈希、采样统计、确认来源文本与矩阵；用户自定义文字可能包含研究信息，界面明确提示检查。

聊天只在当前会话保存最近30轮；待应用计划被新请求替代。评价记录保留最多200条，用户显式下载时才导出；记录类型、状态、revision、改变字段位置、调用次数、耗时及提供的 Token。默认不持久化请求/参数值/模型上下文。工作台工程仍保存原版本格式，不保存密钥/聊天。

## 验收与课程证据

`tests/test_ai.py` 测协议、局部事务、失败不提交、语言/时间/单位、undo/redo、引用、GUI同步、过期状态、API错误及隐私。Provider 测试替代 HTTP 响应，只验证协议实现，不能认定真实模型理解。

`scripts/stage03b_acceptance.py` 使用四份真实数据、十二条固定任务，默认 scripted Mock。`--real --consent-metadata-and-cost` 且配置环境 Key/模型时才调用真实服务，并在独立验收工作区应用合格方案。每条记录用户请求、模型操作、差异、前后 FigureSpec、是否满足独立断言、次数/耗时/Token和错误。六份源文件 SHA-256 核对，工程重开矩阵精确比较，八张双语PDF及PNG/SVG用于本地质量检查。详细研究记录不公开。

`examples/stage03b_public_demo.py` 为明确标注的合成信号脚本演示；没有模型自然语言成功声明。`examples/stage03b_comparison_tasks.json` 为六组手动GUI/运行时LLM/通用编程助手对照协议，records 初始为空。没有实测效率提升或费用结论。

限制：当前真实模型自然语言验收待API配置和外传/费用授权；无持久对话、波形分析、故障分类、任意代码、MCP、自主后台执行。Python3.11尚未实测；当前API协议验证不等于所有兼容厂商实测可用。
