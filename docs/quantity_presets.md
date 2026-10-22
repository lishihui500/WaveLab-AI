# 电气物理量与单位预设

## GUI 使用

1. 将通道加入子图，打开“编辑当前通道名称与单位”。按分类或下拉搜索选择物理量，确认**源数据实际单位**，点击“应用通道物理量与源单位”。推荐 kV/kA 等仅是候选，不代表从波形自动推断；源单位确认不改动采样值。
2. 在“子图、坐标轴与单位”选择“Y轴物理量预设”，直接生成双语名称并使用推荐显示单位。例如源数据为 25000 V，选择电压预设/kV 后，曲线显示为 25，标题为“电压 (kV)”或“Voltage (kV)”。
3. 只改“Y 轴显示单位（换算刻度）”会保留原自定义标题名称。用户编辑名称时不自动翻译；编辑预设生成的标题会转入 custom 模式。需要回到原始数值时，点击“Y 轴显示跟随源单位”。
4. 下拉框可以键盘直接输入任意单位并按 Enter，也可用鼠标选择候选。“添加自定义物理量预设”保存自己的中文、英文名称和单位，获得独立稳定 ID。自定义单位不被强制替换。
5. 分类提供常用、最近使用、全部、电压、电流、功率与能量、控制与频率、电路参数、自定义。最近最多 10 个“物理量＋单位”组合，保存在本地应用偏好 `.wavelab/quantity_preferences.json`，不写入每个工程。

已确认源单位后，常用 Y 轴配置通常只需选择预设，再按需改一次显示单位。旧的自由文本确认入口仍保留，可填写不在预设中的名称与单位。

## 三种单位语义

| 配置 | 含义 | 是否改变原始数组 |
|---|---|---|
| Channel.unit、ConfirmedQuantity.unit、SeriesSpec.unit | 明确确认的源数据单位；旧项目继续沿用此义 | 否 |
| PanelSpec.display_unit | 此子图的统一显示单位；null 表示源单位 | 否，仅绘制时乘比例 |
| ylabel_i18n、自定义标签 | 纯文字；单独修改文字不触发换算 | 否 |

新增 `ConfirmedQuantity.preset_id`、`PanelSpec.quantity_preset_id`，记录稳定预设 ID；`ylabel_mode` 新增 preset，双语名称复用已有 ylabel_i18n 字段，生成时在渲染中追加实际显示单位。自定义标题的保存文字不会被单位下拉框覆盖；显示时替换末尾已识别的单位后缀。老项目缺少新字段时默认 null/原标签模式，旧单位与名字保持原值。

同一子图可以统一显示不同前缀的兼容源单位，例如 V 和 kV。先为子图选择统一显示单位，再添加其他单位的曲线。未指定统一显示单位的混合源单位仍会拒绝，避免把不同数值尺度直接叠加。V 与 A、W 与 var 等不兼容，必须分到不同 Y 轴/子图。

切换显示单位会同步换算手动 panel.ylim 和 inset.ylim，以保持相同物理窗口；局部图 xlim_s、事件秒值、通道顺序、颜色线型线宽和原始数据均不改动。图例若显示单位，使用实际显示单位。标题中的单位与数值刻度一致。

## 单位库与支持的换算

单一注册表：`src/wavelab/quantity_presets.py`。只支持注册的同族 SI 前缀比例换算：

| 类别 | 单位族 |
|---|---|
| 电压 | kV、V、mV |
| 电流 | kA、A、mA |
| 有功功率 | MW、kW、W |
| 无功功率 | Mvar、kvar、var |
| 视在功率 | MVA、kVA、VA |
| 能量 | J、kJ、MJ；Wh、kWh、MWh，两个族分别换算 |
| 时间 | s、ms、μs |
| 频率 | Hz、kHz |
| 电阻 | Ω、mΩ、kΩ |
| 电感 | H、mH、μH |
| 电容 | F、mF、μF、nF |

其他候选：rad/s、rad、°、Hz/s、1、pu、%、°C、K。相同单位允许原样显示，包括自定义单位。此版本不支持 J 与 Wh、rad 与 °、°C 与 K 的跨族转换；不支持用户自建比例/仿射换算。pu、% 可以作为已知源单位，但无基准或明确定义时拒绝与 SI 单位或彼此换算，不能把 kV 换成 pu 或把电压幅值改为百分比。

X 轴原始 Domain 一直为秒；现在完整支持 s、ms、μs，绝对与相对时间、手动范围、框选和局部图均使用同一单位注册表。局部图始终保存绝对秒，不会因显示成 μs 而把时间窗口误缩放一千倍。

## 33 项基础物理量

| 分类 | 稳定 ID 与中英文名称 | 候选 / 推荐默认 |
|---|---|---|
| 电压 | voltage 电压 / Voltage；dc_voltage 直流电压 / DC Voltage；ac_voltage 交流电压 / AC Voltage；capacitor_voltage 电容电压 / Capacitor Voltage；arm_voltage 桥臂电压 / Arm Voltage；dc_link_voltage 直流母线电压 / DC-Link Voltage；dq_voltage dq轴电压 / dq-Axis Voltage | kV、V、mV、pu / kV |
| 电流 | current 电流 / Current；ac_current 交流电流 / AC Current；dc_current 直流电流 / DC Current；arm_current 桥臂电流 / Arm Current；circulating_current 环流 / Circulating Current；differential_current 差动电流 / Differential Current；dq_current dq轴电流 / dq-Axis Current | kA、A、mA、pu / kA |
| 功率 | active_power 有功功率 / Active Power；reactive_power 无功功率 / Reactive Power；apparent_power 视在功率 / Apparent Power | 各自功率族 / MW、Mvar、MVA |
| 能量 | energy 能量 / Energy | J、kJ、MJ、Wh、kWh、MWh / J |
| 时间与频率 | time 时间 / Time；frequency 频率 / Frequency；angular_frequency 角频率 / Angular Frequency；phase_angle 相角 / Phase Angle；rocof 频率变化率 / RoCoF | s/ms/μs；Hz/kHz；rad/s；rad/°；Hz/s / 各首项 |
| 控制 | modulation_index 调制比 / Modulation Index；duty_cycle 占空比 / Duty Cycle | 1、pu、% / 1 |
| 分析 | thd 总谐波畸变率 / THD；efficiency 效率 / Efficiency；voltage_unbalance 电压不平衡度 / Voltage Unbalance；current_unbalance 电流不平衡度 / Current Unbalance | %、1、pu / % |
| 电路参数 | resistance 电阻 / Resistance；inductance 电感 / Inductance；capacitance 电容 / Capacitance；temperature 温度 / Temperature | 对应上述单位族，温度°C/K / Ω、H、F、°C |

## JSON Planner / MCP

新增只读 MCP 工具 `get_quantity_presets` 返回预设 ID、中英文名、单位候选、换算族及最近使用。旧工具及旧 JSON Action 继续有效。两个新 Action 复用现有执行器：

```json
{"action":"set_axis_quantity","panel_id":"读取到的真实ID","changes":{"preset_id":"voltage","unit":"kV"}}
```

```json
{"action":"set_display_unit","panel_id":"读取到的真实ID","changes":{"unit":"V"}}
```

unit=null 恢复源单位。新 Action 不修改 Channel.unit、数据清单或物理角色；源单位未知时拒绝转换，需先由用户在通道编辑器确认。它们仍需正确会话、工程标识、revision、fingerprint，批量预览后原子提交并可撤销。

预设选择、单位编辑与渲染均为本地操作，不调用模型、不重新解析 CSV。元数据视图共享原始只读数组，显示换算从源值单次计算，不把已转换数组当作新源数据。

## 启动与验收

此版本使用 Streamlit 可编辑 selectbox，项目依赖最低版本调整为本机已验证的 1.65。保存已有工程并重启 WaveLab 和 MCP 连接，加载新的配置字段和工具。若 PowerShell 禁止 ps1，可直接运行：

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\app.py --server.address 127.0.0.1 --server.port 8501
```

不要在端口已有实例时重复启动。开发验收应使用独立端口与合成数据。已知源单位 V 的合成 GUI 会话可运行：

```powershell
.\.venv\Scripts\python.exe scripts\verify_quantity_mcp.py --session <真实会话ID>
.\.venv\Scripts\python.exe -m pytest -q --junitxml=reports/quantity_presets/pytest.xml
```


## MCP 统一确认物理量与源单位

新增 `configure_panel_quantity`，与 GUI 的统一设置共用校验。该操作显式更新当前子图全部可见通道的物理量、源单位及其所有绘图引用，同时设置目标轴显示单位。共享引用存在不兼容显示单位时整批拒绝。更换维度时目标主图及局部图旧 Y 范围恢复自动，局部图时间和位置保留。

```json
{"action":"configure_panel_quantity","panel_id":"实际子图ID","evidence_quote":"原始单位 kV","changes":{"preset_id":"voltage","source_unit":"kV","display_unit":"kV"}}
```

`evidence_quote` 必须来自本次 `user_request` 的原话，并明确确认源单位（用户直接回复单位亦可）；不能把“显示为 kV”当作源单位确认。自定义物理量省略 `preset_id`，填写 `zh`、`en`。三个子图可在一个批次提交，一步撤销。仍须匹配 session、epoch、revision、fingerprint。源文件、样本数组、通道身份和物理映射禁止修改。

旧的 `set_axis_quantity` / `set_display_unit` 继续仅修改显示。升级后保存工程并重启工作台及 MCP 连接，让两端加载同一协议；无需修改旧项目 JSON。
