# 阶段 0–3A 核心架构

阶段 3B 在本文既有架构上新增受限模型执行层，详见 [stage03b_architecture.md](stage03b_architecture.md)。FigureSpec schema、解析器、Workbench 和 Matplotlib 引擎保持稳定。

依赖方向：检查 CLI → ingest → domain；绘图 CLI → render → domain / ingest。NumPy 保存二维 float64 矩阵，Pydantic 验证 JSON 元数据，Matplotlib 绘图。阶段3A引入 Streamlit（其依赖包含 Pandas）；阶段3B使用独立 REST Provider，不引入模型 SDK。FigureSpec 颜色字段使用 Matplotlib 颜色校验。

| 对象 | 职责 |
|---|---|
| Dataset | 只读完整样本矩阵；时间列为第 0 列；按 channel_id 读取源列 |
| DatasetManifest | schema、持久化 dataset_id、源路径/哈希、编码、原始表头、通道/组、采样统计、告警 |
| Channel | channel_id、source_column_index、raw_header、group_name、group_index、display_name、unit、physical_role、confirmation_source |
| ChannelGroup | 按原始出现顺序保存成员 channel_id，支持非连续同名列 |
| SamplingInfo | 有效样本数、起止时间、均匀性、采样间隔范围/中位数、均匀采样率、判断容差 |
| ImportWarning | 可序列化告警代码、解释、源行号；导入界面将来负责展示 |
| ParseError | 结构化错误代码、源行号和 0 基列号；校验失败时不返回删减数据集 |

数据身份生命周期：新导入生成 UUID → 保存 manifest → 用户修改名称/单位/映射并创建新 manifest → `reopen_file` 以保存的 ID 重读源文件 → 核对 SHA-256 和列/采样信息 → 按原列恢复身份和映射。相同内容再次独立导入属于新的数据集；文件内容哈希是完整性证据，不替代数据集身份。

`map_group` 要求非空确认来源，通道数必须与模板一致。解析过程不自动应用测试集1六桥臂顺序；真实数据测试中显式采用交接文档记录的用户确认。三维变量保持原序编号，待用户确认再应用 ABC。无需确认物理语义也能完成通用数据导入。

`render` 已消费 Dataset 和经过验证的 FigureSpec；阶段3A的 `workbench.py` 校验字段更新、引用和撤销；`app.py` 调用统一入口，后续 AI 可复用结构化接口。FigureSpec 只保存绘图意图、无数组的 DatasetManifest 和 channel_id 引用，相对事件时间仅转换显示坐标。

## 阶段 2 绘图契约

阶段2的初始 schema 为 `0.2`（阶段3A已升级为0.3并保留兼容读取）：PageSpec 定义尺寸/字体/dpi；TimeAxisSpec 定义绝对或相对时间、s/ms、原始事件秒值及显示 xlim；PanelSpec 定义纵向子图、独立 y 范围/科学计数法；SeriesSpec 以 channel_id 引用源列，保存显式标签、单位和样式；LegendSpec 支持图外上方或隐藏；EventSpec 保存原始秒值、目标子图及确认来源。

结构校验检查重复数据集/子图/曲线引用、缺失通道、共享轴范围冲突、非有限/倒置范围、合法样式、单位/角色与确认映射冲突。物理角色和事件含义要求可追溯来源。渲染入口重新校验 schema 并核对 Dataset 清单，不能用 display_name 或 raw_header 查值。

`render/engine.py` 使用 Figure + FigureCanvasAgg，不开启 pyplot/GUI，不依赖 LaTeX。局部 rc_context 管理等效 IEEE 样式、宋体/字体回退、无网格、无路径简化、无时间戳输出。独立图例行隔离曲线区；自动布局后固定位置，避免导出后端字体测量造成漂移。SVG 仅规范化自动剪裁/标记 ID，不改曲线路径坐标。

RenderResult 保留 Figure、按 panel_id 索引的轴、按 `(panel_id, channel_id)` 索引的曲线、字体和警告，供后续展示与测试。相对时间计算生成新数组；y 来自源通道，范围仅裁剪显示。save_spec/load_spec 保存 JSON；reopen_datasets 依源路径重读并核对原哈希，以 JSON 所在目录为 base_dir 可解析相对路径。阶段3A工程目录包含独立副本，支持目录迁移；ZIP工程打包仍待后续实现。

PDF/PNG/SVG 栏宽固定，PDF 嵌入 TrueType、SVG 文字转路径。同环境测试配置复读的像素与文件字节复现；跨 OS、字体或 Matplotlib 版本可能出现字形/抗锯齿变化，JSON 保存绘图意图而非跨环境二进制同一性。

`render/demos.py` 将六份真实数据与补充局部视图写入被忽略的 `reports/stage_02/`。计时分为 Figure 构建+Agg 绘制、各格式导出、源重读复画，初始解析不计入绘制耗时。此节描述阶段2的绘图基础；阶段3A扩展如下。

原始文件保护：解析入口只有 `read_bytes`；CLI 仅 stdout 输出；写清单由调用者指定独立派生路径。真实样本验收先核对已记录哈希，再比较导入前后字节。不要向公开仓库提交 fixture 和由其计算的研究统计；Git 忽略规则只提供默认保护，不能替代后续公开权限审查。


## 阶段 3A：单一状态与双语模型

`FigureSpec schema_version=0.3` 是唯一图形状态。`BilingualText {zh, en}` 附加于 series.label_i18n、time_axis.label_i18n、panel.ylabel_i18n、panel.title_i18n、event.label_i18n。旧的 label/title/ylabel 仍作为回退值，0.2 在验证入口迁移版本号并填充新字段默认值，不猜测旧标签语言、不自动翻译。再次保存写出0.3；未知版本拒绝。`languages.legend` 与 `languages.axes` 分开选择。缺少英文标签会保留原变量/显示名称并提示。

单位在 Channel / SeriesSpec 独立保存。语言切换不改变单位和数据身份。英文预设用 Times New Roman，中文预设用 SimSun；混合语言通过独立图例字体和中文字体逐字回退。不存在的主字体/图例字体发出提示。Matplotlib 数学排版不依赖外部 LaTeX。

PageSpec 新增轴标题字号、子图标题字号、子图间距和顶部图例行间距；LegendSpec 支持顶部、右侧外部、四个内部角落、隐藏及独立字体/字号/列数。SeriesSpec.visible 支持隐藏；允许子图暂时没有曲线。空工程不创建虚假数据，用 `spec=None` 表示。至多12个纵向子图，至少保留一个。

## 统一修改接口

`Workbench.update(path, value)` 只更新指定路径，完整 Pydantic 验证与数据引用核查成功后由 `commit` 提交。路径只允许存在的图形字段，不能直接更新数据清单。复合表单通过 `commit(payload)` 一次提交；通道名称/单位、映射、曲线移动有独立方法，最后均走 commit。拒绝非法颜色、倒置范围、未知引用、同轴混合单位、无来源物理角色，以及原始哈希、列序、采样信息等身份字段的改变。阶段3B增加受限AI操作；无任意代码执行或MCP服务。

成功提交保存旧 FigureSpec 快照（最多50步），清空 redo；无变化不新增历史，校验失败不改变状态。undo/redo 恢复完整配置，包括映射。样本只读缓存按 dataset_id 保留；渲染使用**当前配置中的 manifest**，因此撤销映射后不会残留另一份元数据。界面控件以 revision 更新键，保证撤销、打开工程和预设后重新显示当前值。表单中的暂存输入只在点击应用后成为配置，不作为渲染参数。

## 持久化与缓存

导入入口 `import_bytes` 将原始字节写入 `.wavelab/imports/<sha256>.txt`（排他创建；已存在则比对字节，不覆盖），再复用阶段1 `parse_file`。粘贴文本采用 UTF-8；原有 UTF-8 BOM / GB18030 上传文件逐字节保留。源文件路径与数据内容不被写回。

工程保存将每份导入数据复制到工程 `data/` 内，以哈希命名；project.json 包含 `project_version=1`、完整 FigureSpec 和数据集展示名称。数据引用为相对路径；工程清单通过临时文件和 `os.replace` 原子替换。再次保存同名工程更新清单，旧内容寻址数据副本保留。每次保存先校验字节哈希。恢复限定副本在工程 data 目录内，逐个重读、验证哈希和采样/表头；所有数据验证成功后再替换会话状态，失败保留当前工程。只复制工程目录到另一位置即可恢复。

数据解析仅发生在导入、打开工程或打开独立JSON时。手动标签/样式编辑直接使用内存全样本矩阵。`st.cache_data(max_entries=8)` 缓存按完整 FigureSpec JSON 标识的预览PNG（含数据哈希和稳定ID）；预览140 DPI、导出按配置DPI，几何布局来自相同绘图引擎。未实施预览降采样，也未引入隐式统计降采样。

双语导出从当前 FigureSpec 创建两个临时视图，只更改语言和默认字体，写入独立批次目录；不写回工作台、不增加撤销记录。PDF、SVG 和预览共享 Agg 计算后冻结的布局。页面边界检查对可能裁切给出告警；任意长标签并不保证自动排得下，可通过宽高、字号、列数和间距调整。

## SVG 后续扩展

当前保持 `svg.fonttype=path`，用于显示兼容。后续在受验证的输出设置中加入 `svg_text_mode`：`path` 显示兼容模式、`text` 后期编辑模式（文本对象，需接收端字体）。此项不阻塞3A，本阶段尚未实现文本对象导出。

## 验证边界

阶段0–2测试保持不变；新增服务测试和 Streamlit AppTest 通过真实控件执行导入、选择、属性编辑、双语切换、撤销恢复和新会话重开。独立验收脚本使用四个真实场景生成本地结果、比较CSV独立数值矩阵并检查所有源文件哈希。AppTest不模拟操作系统文件选择器和浏览器下载；这些环节结合实际浏览器运行截图和人工步骤验收。性能记录区分首次绘图、导入和导出，不代表跨机器基准。

Matplotlib 的 rc_context 使用进程级设置，阶段3A在绘图、导出和预览PNG写出时使用可重入锁，避免多浏览器会话并发串扰。运行配置关闭开发热更新；更新代码需重启服务，已有工程从磁盘恢复。
