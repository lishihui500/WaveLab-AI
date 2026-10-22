"""Write final reports from measured records; no experiment actions or invented observations."""
from pathlib import Path
import json,statistics
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/stage_03F'
records=json.loads((OUT/'benchmark_results.json').read_text(encoding='utf-8'))['records']
groups=json.loads((OUT/'statistics.json').read_text(encoding='utf-8'))['groups']
def write(name,text):(OUT/name).write_text(text.strip()+'\n',encoding='utf-8')
def f(x):return 'N/A' if x is None else f'{x:.3f}'
def table(method):
    rows=['|任务|观测轮数/有效计时数|均值 ± 样本标准差 / s|中位数 / s|最小–最大 / s|首次严格通过|最终严格通过|','|---|---:|---:|---:|---:|---:|---:|']
    for g in groups:
        if g['method']!=method:continue
        t=g['timing']['task_s'];rows.append(f"|{g['task_id']}|{g['executed_n']} / {t['n']}|{f(t['mean'])} ± {f(t['sample_std'])}|{f(t['median'])}|{f(t['min'])}–{f(t['max'])}|{g['first_attempt_success_count']}/{g['first_attempt_observed_n']}|{g['final_success_count']}/{g['final_observed_n']}|")
    return '\n'.join(rows)
mcp_table=table('codex_mcp');gui_table=table('gui_automation')
calls=['|任务|各轮任务观察 / s|平均 MCP 往返 / s|其中 apply / s|其余查询 / s|各轮工具调用数|','|---|---|---:|---:|---:|---|']
for task in ['F01','F02','F03']:
    rs=[r for r in records if r['task_id']==task and r['method']=='codex_mcp'];mean=lambda field:statistics.mean(r['timing'][field] for r in rs)
    calls.append('|'+task+'|'+', '.join(f(r['timing']['task_s']) for r in rs)+'|'+f(mean('mcp_total_s'))+'|'+f(mean('apply_roundtrip_s'))+'|'+f(mean('mcp_total_s')-mean('apply_roundtrip_s'))+'|'+', '.join(str(r['mcp_calls']) for r in rs)+'|')
calls='\n'.join(calls)

write('performance_analysis.md',f'''# 阶段 3F-A 性能与效率分析

实验：2026-10-18 至 19，Asia/Shanghai。仅作小样本描述统计，保留失败轮次。人工 GUI 与 ChatGPT 手动 JSON 均为 NOT_MEASURED。

## 真实 Codex + MCP

{mcp_table}

{calls}

共42次已记录工具调用，9次绘图事务全部首次执行成功。严格任务配置通过7/9：F02 R2/R3选用了#E69F00，固定验收要求#D55E00。原自然语言仅写“橙色”，因此该差异说明配色协议没有充分传达到模型，不能据此认定模型不理解橙色。失败记录保留，没有事后改变色号或验收规则。

R1三任务在根聊天上下文执行；R2/R3六任务在另一个无继承历史的Agent上下文执行。共两个上下文，各自内部共享历史，不具有九次统计独立性。R1每轮4个调用，schema发现发生在轮次外；R2/R3每轮5个调用，包含schema读取。查询成本和规划背景并非完全一致。

task_s从首次status查询前至最终context回读后，包含模型编排、查询与工具等待。MCP往返含排队、验证、试绘与传输。其余查询耗时为已测工具时长的分类求和，不是模型推理时长。纯推理、内部渲染和Token均N/A。

## 真实 GUI 自动化

{gui_table}

F01 R1原始墙钟48442.411s，跨越会话暂停，整条计时不纳入统计，质量结果仍保留；R4从新副本补齐第三个有效计时。F03 R1的123.448s及失败均保留：恢复时重复创建B相局部图，最终不满足每图一幅。F02 R1的48.984s包含轮次内编排等待，后两轮24.412/25.690s；日志另给真实控件编辑区间22.862/24.411/25.690s，不以该次级口径替换主记录。

GUI主计时实际为“初态就绪标记至最终DOM回读”，含操作、状态查询及Agent编排。保存/双语导出另测；完整含后续独立验收和视觉检查的end_to_end_s未连续测得，留空。F01 R2/R3保存导出观察还包含跨工具轮次等待，不能当成磁盘或渲染纯耗时。page_load_s仅在同一调用内从打开按钮至工程回读可靠测得时填写；F01准备与加载混合字段另存，不冒充页面加载。

控件交互数以实际成功输入事件计：选择=展开点击+选项点击，自动输入=fill+Enter，表单fill和按钮激活各1。完整日志可核的F01有效三轮均18次；F02为42/44/44次；F03无错误两轮各15次。重试轮的总交互数N/A，另存成功交互下界。GUI rerun次数没有可靠观测，不按修改次数推算。

## 同口径比较和解释

同初态由基准哈希与持久通道身份核验，两方式的计时入口不同，F02还存在色号协议歧义，F03模型自主选择的局部图bounds与GUI默认值不同。因此同口径加速比表为空，不计算节时率。GUI自动化的中位观察在本机三任务均低于MCP，但它使用针对任务编排的控件流程，不包含真实人的学习和操作成本，无法推出人工效率排名。

F01分组和F03批量局部图体现模型跨对象规划与事务一致性的价值；F02也可批量设置，但明确颜色编码后才能严格比较。简单单字段本地GUI可能更直接。小样本、固定任务顺序、热服务、跨日测量、GUI适配过程以及错误恢复均影响波动。首轮较慢可由编排/适配解释，缺少受控冷热启动与交错随机顺序，不能单独归因缓存。

图：figures/task_times.png、mcp_calls.png、success_counts.png及对应PDF/SVG。全部明确GUI automation ≠ human GUI。原始结构化记录为benchmark_results.csv/json，完整统计为statistics.json。
''')

write('correctness_report.md','''# 阶段 3F-A 独立正确性检查

19份保存工程已逐份重开、验证配置和源数据，结果见final_acceptance_index.json及artifacts/*/acceptance.json。

|检查|结论|
|---|---|
|MCP严格任务配置|7/9通过；F02两轮固定色号不一致，保留FAIL|
|GUI严格任务配置|9/10通过；F03 R1的B图有两幅重叠局部图，保留FAIL|
|源文件、工程数据副本、时间与全部样本|19/19一致；601行、6通道合成数据，原数组逐元素核对|
|保存→销毁Workbench→全新实例重开|19/19配置和数组复现；每轮重新渲染|
|主图和局部图实际数组/样式|逐点核对主图全采样、局部窗切片、X坐标、颜色/线型/线宽继承；通过|
|双语导出|每轮PNG/PDF/SVG，中文和英文各一份；PNG及PDF实际栅格检查|
|程序化几何|19/19图例处于画布内且不交主axes；实际绘制标题、轴标签、刻度不裁切；局部图实际bounds在父图内并匹配配置|
|像素视觉检查|76张PNG/栅格图按像素哈希分24组；六张contact sheet全部实际查看，字体、单位、标题、图例无严重裁切|
|既有文件保护|321个受保护文件SHA-256一致，含原始样本、既有工程和3E证据|
|产品源码保护|environment.json列出的app.py及src/wavelab Python文件最终哈希均不变|

几何检查原先把Matplotlib缓存的1.20/1.95窗外刻度当作实际绘制文本，误报裁切。根据本机Axis._update_ticks实际绘制集合修正验收工具，1px边界容差保持不变；旧九份验收记录备份在tool_checks/before_drawn_tick_fix。错误报告没有改写为产品修复。

GUI F03 R1的两幅B局部图位置和曲线完全重叠，视觉外观几乎相同；独立配置检查准确发现重复。这证明可见图形和成功提示不足以代替结构验收。其legibility检查通过，整体任务仍为FAIL。

局部图覆盖部分重复稳态波形，目标1.40–1.44s主图窗口未受严重遮挡；本组合成数据没有已确认故障关键区，因此不能推广为真实故障图的遮挡保证。visual_review.json记录实际审阅与等像素依据，image_equivalence_groups.json列出所有成员，review_sheets/保留审阅页。

最后全量回归399 passed，144.42s，见pytest_final.log/xml。新增11项针对验收工具的正负例测试：无关字段、遗漏/重复曲线、不同bounds、源数据篡改、NumPy标量和实际绘制刻度。阶段初始388 passed、137.99s单独保留，不与最终数量相加。
''')

write('issues_and_fixes.md','''# 阶段 3F-A 问题与最小修复

本阶段未修改产品源码。发现的问题分为实验协议、GUI自动化执行和辅助验收工具，不将它们混称为产品缺陷。

1. **F02颜色协议歧义**：模型两轮自主选用橙色#E69F00，验证器固定#D55E00。原提示只写橙色。保留两轮严格FAIL；下一轮把明确hex编码同时写入实际模型提示与GUI目标。没有事后修改本轮参数或放宽断言。
2. **GUI首轮控件适配**：部分Playwright click无响应；option为不可直接press的div；搜索型combo的Space输入了空格。改用新鲜AX索引展开/选择，按钮聚焦后Space。F01 R1重试和跨暂停墙钟保留，补R4独立样本。
3. **GUI F03恢复重复**：切换父图后，旧局部表单仍在替换，fill发生目标失效；恢复过程中B局部图创建结果未充分回读，导致重复。保留最终FAIL。后两轮等待旧局部表单消失后再编辑并通过。没有为浏览器测试新增后门。
4. **验收JSON序列化**：NumPy bool不能直接json.dump，最小转换np.generic.item()。首次异常保留validator_failure_before_fix.log；新增回归。
5. **几何假阳性**：窗外缓存tick不参与实际绘制。使用安装版本Axis._update_ticks的实际draw集合，记录排除原因，未改变1px边界标准。旧验收备份及“窗内真实裁切仍失败”的回归保留。
6. **日志trial变量与计数**：浏览器辅助函数捕获旧trial值，部分原始事件标签为null/旧轮次，初算interaction_count为0。原始JSON保持不变，依据实测半开时间区间和DOM工程名生成gui_event_assignment.json重新归属、计数；DOM校验失败会中止。恢复轮缺少完整失败事件计数，总交互数N/A，保留成功操作下界。
7. **离线计时页浏览器自测限制**：浏览器工具拒绝file协议，未尝试绕过URL策略。通过隔离Node VM测试计时、按钮、JSON和CSV转义，见tool_checks/timer_tool_test.json；真实浏览器UI自测标BLOCKED，人工测试仍NOT_MEASURED。

产品源码哈希不变，399项回归通过，本轮没有复现必须阻止日常手动绘图/工程保存/MCP使用的未修复确定性产品缺陷。长期稳定性和其他机器版本不在此结论内。
''')

write('limitations.md','''# 阶段 3F-A 实验限制

- 每任务每方式仅3个有效计时，失败仍计入；GUI另有1条跨暂停记录，原始48442.411s保留但不进入性能统计。小样本仅作描述分析。
- MCP共两个模型上下文，内部重复共享历史；GUI复用已编排控件流程。不能声称九个统计独立模型会话，也不能把GUI脚本当人工行为。
- MCP先执行、GUI后执行，并跨日/跨会话暂停；没有随机交错顺序或受控CPU温度、系统背景负载和冷启动实验。服务为热启动。
- 浏览器视口未固定：模型Agent截图1280×720，GUI各轮截图为377×427、484×602或377×451。尺寸记录见browser_screenshot_sizes.json及逐轮screenshot_size_px；仅代表截图时刻。响应布局和自动化等待受此影响，不能据此作严格跨路径效率比较。
- 主任务、GUI保存导出、独立磁盘重开导出和实际视觉检查是不同区间；完整端到端连续计时N/A。GUI部分墙钟包含工具编排等待；纯模型推理、内部渲染、Token、可靠rerun数N/A。
- 主时间边界不同，没有计算速度比；F02色号协议未充分统一，F03自主bounds与GUI默认bounds不同。禁止从描述数字推出人工效率或普适AI优势。
- GUI首次适配及恢复错误保留：F03首轮B局部图重复，整体FAIL；其图像几乎重叠，视觉检查不能取代配置验收。
- 只使用601点六通道合成数据做对照；真实科研原始文件仅哈希保护，没有自动外传。未验证大数据量下本次重复实验的性能。
- 实测Python3.14.7及当前Windows/字体环境；未实测Python3.11和其他平台。版本信息见environment.json。
- 人工GUI、ChatGPT手动JSON均NOT_MEASURED；计时工具仅隔离代码级自检通过，file协议受工具安全策略阻止，浏览器UI自检BLOCKED。
- 本项目应用预训练LLM的理解、规划与工具使用，没有自行训练网络。未核实额外课程评分细则，不能替课程教师判断最终课程合格性。
''')

write('stage_03F_A_report.md',f'''# WaveLab AI 阶段 3F-A 综合报告

实验日期：2026-10-18 至19，Asia/Shanghai。**自动化评测、独立验收、人工补测准备和课程初稿已完成；保留3项严格配置失败及1条中断计时，不宣称全部任务达标或AI更快。**

## 已完成结果

- 三个只读合成基准、18份原计划运行副本、3个人工起始工程；F01另补独立GUI R4。原始/既有数据未改动。
- 9轮真实Codex+MCP，42次已记录工具调用，9次事务首次执行成功；严格任务首次/最终通过7/9。
- 10轮真实GUI操作，9个有效计时；严格配置最终9/10通过。中断首轮仍有完整质量结果，失败及重试均保留。
- 19份工程逐份完成配置、数组、文件哈希、保存关闭重开、双语六格式导出和图像检查。321个受保护文件与产品源码哈希一致。
- 最终全量pytest：399 passed in 144.42s。独立计时工具代码自检通过，人工操作数据NOT_MEASURED。

## 真实模型结果

{mcp_table}

MCP主时间：首次status之前至最终context回读之后。F02失败为固定色号不一致：原自然语言“橙色”没有指定hex，模型选#E69F00，验证器要求#D55E00。该协议歧义公开保留。

## GUI自动化结果

{gui_table}

GUI主时间：初态就绪标记至最终DOM回读。F01 R1跨暂停48442.411s，整条计时无效并补R4；F03 R1有两次控件恢复错误，最终B图有两幅重叠局部图，123.448s失败时间仍统计。GUI自动化不代表人工GUI。两方式边界不同，不计算加速比。

## 用户十个问题的回答

1. **重复稳定性**：本组9次MCP事务全部首次执行；F01/F03严格3/3，F02严格1/3。结果仅覆盖三个明确任务和两个共享模型上下文。
2. **时间与波动**：完整三轮、均值、中位数、极值、样本标准差见上表及performance_analysis.md。所有失败轮保留；跨暂停观察整条排除并公开原因。
3. **工具成本**：MCP各任务平均往返18.978/18.535/18.723s，其中apply为5.277/5.280/5.357s，其余已测查询为13.701/13.255/13.366s。纯模型推理不可拆分。
4. **GUI与MCP差异**：本机GUI中位观察14.943/25.690/9.293s，MCP为34.517/35.460/32.536s；GUI包含定制控件流程，首轮适配使均值显著波动。不同边界、任务协议差异及顺序效应禁止计算严格加速比。
5. **能否说明人工效率**：当前没有真实操作者。需从相同初态记录人工阅读、操作、复制/粘贴、检查、修正及保存时间，注明经验和顺序，再比较。
6. **自主规划价值**：模型按实时ID、顺序、映射和版本组织跨对象事务，能够把分相、双语设置、统一局部窗变为受校验操作；固定脚本执行已知任务可更直接，但需预编具体流程。本轮证明工具使用参与，未证明任意任务泛化优势。
7. **后续人工任务**：先做F01/F02/F03各1次人工GUI，共3项；再选1–3项ChatGPT手动JSON，共4–6项起步。若两种方式三任务均各3轮，则18项人工实验。工程、计时页、CSV模板及指南已准备。
8. **日常使用阻碍**：未发现需阻止核心科研使用的已复现未修复产品缺陷。已见问题属于测试适配、恢复操作及实验/验收工具；产品源码未改，399项回归通过，长期稳定性仍需日常观察。
9. **课程AI作用证据**：自然语言、真实工具请求/返回、配置差异、最终科研图和独立验收能证明预训练LLM在本组三任务的规划与工具使用作用。没有训练网络、训练集或模型精度实验，未核实额外评分细则。
10. **下一步**：先把下一轮明确色号写进实际模型提示，并采用已验证的表单等待/提交后回读流程，再进入3F-B人工补测。当前无需大规模产品重构。

## 交付索引与复现

- 协议/初态：benchmark_protocol.md、task_prompts.md、initial_manifest.json、supplemental_initial_manifest.json、baselines/、runs/、manual/。
- 原始记录：mcp_trace.json、agent_mcp_trace.json、agent_mcp_gui_trace.json、gui_events.json、gui_timing.json、gui_event_assignment.json、trials/。
- 汇总：benchmark_results.csv/json、statistics.json、performance_analysis.md、correctness_report.md、issues_and_fixes.md、limitations.md。
- 验收：artifacts/、final_acceptance_index.json、configuration_diffs.json、source_integrity.json、product_source_integrity.json、visual_review.json、image_equivalence_groups.json、review_sheets/。
- 人工：manual_test_guide.md、manual_timer.html、manual_test_record_template.csv、manual/F01_manual_start、F02_manual_start、F03_manual_start。
- 课程：course_report_draft.md、architecture.md、demo_cases.md、figures/。浏览器最终截图gui_final_full.png；原始失败证据和旧验收在tool_checks/。
- 脚本位于项目scripts/stage03f_*.py及stage03f_timer_check.mjs；命令见acceptance_tools.md。准备脚本拒绝覆盖已存在初态；后处理脚本不执行被测绘图动作。
- GUI复现见gui_automation_procedure.md；环境版本见environment.json、requirements_snapshot.txt、browser_screenshot_sizes.json。图像审阅授权按review_approved_pixels.json中的已检查像素哈希绑定，新图像不会由records脚本自动追认。

```powershell
.\\.venv\\Scripts\\python.exe -m pytest -q --tb=short
.\\.venv\\Scripts\\python.exe scripts/stage03f_finalize.py
.\\.venv\\Scripts\\python.exe scripts/stage03f_records.py
.\\.venv\\Scripts\\python.exe scripts/stage03f_summarize.py
.\\.venv\\Scripts\\python.exe scripts/stage03f_charts.py
.\\.venv\\Scripts\\python.exe scripts/stage03f_integrity.py
```

finalize为独立验收/导出，records只整理已发生的真实证据；两者均不能替代新的模型规划或GUI测试。visual_review.json对应本次已经实际查看的图像；修改图形后需重新查看，不能以自动重写PASS替代。
''')

course=(OUT/'course_report_draft.md').read_text(encoding='utf-8')
course=course.replace('作者完成数据契约、确定性程序、受限工具、工作台与实验设计；模型在实际任务中完成自然语言到操作序列的规划。','用户提供领域需求、原始样本、物理语义确认并审核结果；Codex参与程序、测试与文档实现。运行期Codex完成自然语言到操作序列的规划，确定性程序完成验证与渲染。开发中的AI协助和应用运行期的AI规划分别记录，不能把全部工程实现归为人工工作。')
start=course.index('## 自动化与真实模型结果')+len('## 自动化与真实模型结果')
end=course.index('## 效率、可靠性与 AI 能力边界',start)
course=course[:start]+f'''实验于2026-10-18至19执行。9轮真实MCP事务执行9/9，严格配置7/9；两项颜色差异按固定协议保留失败。GUI共10轮，其中9条有效时间，严格配置9/10；一项局部图重复失败，一项跨暂停时间保留但不进入性能统计。最终399项pytest通过，321受保护文件及产品源码哈希不变。

{mcp_table}

{gui_table}

图表与真实案例见figures/和demo_cases.md。GUI自动化不等于人工GUI；完整端到端计时、Token、纯推理与内部渲染N/A。不同时间边界不计算加速比。独立配置验收发现视觉近乎相同的重复局部图，说明结果检查必须同时覆盖结构与实际图像。

''' +course[end:]
course=course.replace('## 自动化与真实模型结果实验于','## 自动化与真实模型结果\n\n实验于')
write('course_report_draft.md',course)

write('demo_cases.md','''# 课程典型案例材料

全部为明确标注的601点六通道合成波形，原始表头重复Ucap；物理映射已显式确认。以下三个成功样例与失败证据均为实际结果，未预制模型回答。

|任务|初态图|真实模型成功图|调用记录|验收|
|---|---|---|---|---|
|F01六桥臂分相|figures/F01_initial_en.png|artifacts/mcp_F01_R1/final_en.png|mcp_trace.json 中F01_R1|artifacts/mcp_F01_R1/acceptance.json|
|F02样式与双语标题|figures/F02_initial_en.png|artifacts/mcp_F02_R1/final_en.png|mcp_trace.json 中F02_R1|artifacts/mcp_F02_R1/acceptance.json|
|F03统一局部图|figures/F03_initial_en.png|artifacts/mcp_F03_R1/final_en.png|mcp_trace.json 中F03_R1|artifacts/mcp_F03_R1/acceptance.json|

![F01初态](figures/F01_initial_en.png)
![F01实际完成](artifacts/mcp_F01_R1/final_en.png)
![F02实际完成](artifacts/mcp_F02_R1/final_zh.png)
![F03实际完成](artifacts/mcp_F03_R1/final_en.png)

各目录同时有中文/英文PNG、PDF、SVG，initial_figure.json与final_figure.json，configuration_diffs.json保存19轮真实字段差异。准确自然语言见task_prompts.md；真实请求和返回含session、epoch、revision、fingerprint，保留于两个MCP trace。逐轮时间、调用、错误及质量结果见benchmark_results.json。

失败案例一：MCP F02 R2/R3采用#E69F00，不符合固定#D55E00协议。失败案例二：GUI F03 R1恢复后B图出现两幅重叠局部图，图像几乎相同但独立结构验收失败。两者适合说明协议精确性与确定性校验的必要性，不用于掩饰软件性能。

结果图表：figures/task_times.png、mcp_calls.png、success_counts.png及对应PDF/SVG。所有图表明确GUI自动化与人工操作不同，人工方式NOT_MEASURED。architecture.md给出自然语言→模型→MCP→Bridge→Workbench/校验→Matplotlib→工程/图形的分工。
''')

protocol=(OUT/'benchmark_protocol.md').read_text(encoding='utf-8').replace('首次目标编辑前至最后目标状态可见并回读；boundary=`first_edit_to_final_visible`','实际初态就绪标记至最后目标状态可见并回读；boundary=`initial_ready_marker_to_final_visible`，包含轮次内Agent编排；另外从日志提供首个真实控件事件到终点的editing_interval_s')
protocol=protocol.split('\n## 本次实际偏离与处理',1)[0]
protocol+='\n## 本次实际偏离与处理\n\nMCP先测、GUI后测，未交错；R1与R2/R3共两个模型上下文。GUI F01首轮跨暂停48442.411s，保留质量与原始墙钟，整条计时排除并补独立R4。F02精确hex未充分传入两轮模型提示，严格失败公开保留；F03模型与GUI可使用不同的合格bounds。GUI F03首轮重复局部图失败保留。完整端到端连续计时未取得。上述偏离限制效率解释，不以补写协议追认失败为成功。\n'
write('benchmark_protocol.md',protocol)
guide=(OUT/'manual_test_guide.md').read_text(encoding='utf-8')
guide=guide.split('\n## 本轮补充说明',1)[0]
begin=guide.index('每轮先点击计时器“开始”')
end=guide.index('## 独立验收与图像复核',begin)
guide=guide[:begin]+'每轮先点击计时器“开始”，完成目标后使用新工程名保存。填写结果、操作次数、重试与备注后点击“结束”，下载CSV/JSON。该区间为绘图加保存；随后再导出PNG/PDF/SVG、关闭重开并独立验收，另行保留起止时刻。未连续测量完整流程时，端到端字段留空，不把绘图加保存时长冒充完整端到端时长。失败后保留首次记录，修正另记，不重置起点掩盖失败。不记得的次数留空。\n\n'+guide[end:]
guide+='\n## 本轮补充说明\n\n开始前明确蓝#0072B2、橙#D55E00，避免口头颜色歧义。切换父图后等对应局部图表单更新，再输入窗口和提交；提交后查看已有局部图列表，避免重复创建。计时页结束按钮会采集当前结果、次数和备注，请结束前填写。计时页没有全局交互监听；其隔离代码自测通过，当前浏览器工具不允许file协议，因此浏览器UI自测BLOCKED，未绕过安全策略。你以后可按正常本地文件方式打开HTML；本轮没有记录任何真实人工操作数据。\n'
write('manual_test_guide.md',guide)
print('Final reports written from 19 automated trials and 6 unmeasured human slots.')
