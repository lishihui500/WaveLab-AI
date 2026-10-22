"""Build descriptive experiment report from observed records, without rescoring."""
from pathlib import Path
import json,statistics
R=Path(__file__).resolve().parents[1];O=R/'reports/stage_04';B=O/'formal_v2'
s=json.loads((B/'statistics.json').read_text(encoding='utf-8'));rows=s['rows']
lines=['# Stage 4 正式实验分析','',f"已归档主要批次 {len(rows)}/24 轮，严格完成 {sum(x['strict_pass'] for x in rows)}/{len(rows)}；用户追加 GUI T2 补测 {s['supplemental_observations']} 轮，独立列示。Pilot 不计入正式统计；旧编排异常首轮原始记录保留于 formal/ 与 history/。",'',
'## 分任务结果','', '|任务|方式|严格完成|95% Wilson区间|原子确认/全部要求|未测量原子|300秒删失后中位数/s|','|---|---|---|---|---|---|---|']
for g in s['summaries']:
 n=g['started_n'];lo,hi=g['wilson95'];ci=f'{lo:.1%}–{hi:.1%}' if n else '未测量';med=g['median_observed_s']
 lines.append(f"|{g['task']}|{g['method']}|{g['strict_passes']}/{n}|{ci}|{g['atoms_passed']}/{g['atoms_total']}|{g['atoms_unmeasured']}|{med:.3f}|" if med is not None else f"|{g['task']}|{g['method']}|0/0|未测量|0/0|0|未测量|")
lines += ['', '原子比例以逐项配置检查为依据；未保存工程的轮次无法获得可靠最终配置，标记未测量。不能把未测量当成已满足或已测不满足。T2含66项原子，其权重高于其他任务，跨任务总原子率不能代替各任务严格完成率。n=3仅支持本次任务与环境的描述，区间较宽。', '', '## 全部轮次与失败原因','', '|顺序|轮次|结果|耗时/s|原子|数据一致|GUI保存重开|原因|','|---|---|---|---|---|---|---|']
for r in rows+s['supplemental_rows']:
 lines.append(f"|{r['order']}|{r['trial_id']}|{r['status']}|{r['task_s']}|{r['atoms_passed']}/{r['atoms_total']}（未测{r['atoms_unmeasured']}）|{r['data_consistency']}|{r['save_reopen']}|{r['failure_reason'] or '无严格失败'}|")
lines += ['',f"原24轮操作时间按300秒超时右删失累计 {sum(r['time_censored_s'] for r in rows)/60:.2f} 分钟；不含预检和独立验收。这个累计量不等于全部成功完成任务的用时。"]
for r in s['supplemental_rows']:
 lines += ['',f"补测 {r['trial_id']}：{r['status']}，{r['atoms_passed']}/{r['atoms_total']}项，耗时{r['task_s']}秒，已保存和GUI重开部分产物。三幅局部图完整性门槛未满足；inset_ids_unique字段还检查三幅齐全，False不能单独解释为保存产物存在重复ID。"]
lines += ['', 'GUI T2原R1虽已保存并达到66/66，但未在截止前完成真实GUI重开，保留TIMEOUT。R2/R3未完成保存，验收器的FileNotFound及最终GUI观察均保留。补测不能替换原R1或进入原24轮完成率。GUI T4 R2在资源中断前已保存并取得打开返回，最终GUI核实未完成；保留TIMEOUT_RESOURCE_INTERRUPTION。其保存产物通过配置/数据/拒绝恢复检查，不能据此追认为预算内完整完成。拒绝副本从evidence目录按原字节适配至验收期望路径，原件及说明保留。', '',
'MCP T2 R3最终配置66/66且保存重开，但原始MCP返回缺失，严格失败。MCP T4 R1最终范围及数据检查通过，但缺少拒绝原始返回和拒绝前上下文；拒绝与中间状态保护无法完整核验，严格失败。日志缺失不能证明工具执行错误，也不能据最终状态补造历史返回。原始验收错误和局部证据验收说明同时保留。', '',
'## 公平性、计时与独立性','',
'两组使用相同完整任务、初态文件哈希、原子与验收标准，固定种子20261020按冻结顺序交错执行。每轮fork_turns=none，明确禁止读取其他轮/评分器/历史答案；共享文件系统不是安全沙箱，隔离证据来自读取清单与会话记录。GUI为实际模型自主CUA操作，MCP为真实结构化工具，没有用固定绘图脚本生成任务结果。环境准备与验收不计入任务操作时间，两组均须GUI保存及从保存工程真实重开。', '',
'上述设计纠正了Stage3F的主要设计问题，但实际实施仍有偏离：部分轮次丢失原始日志；部分守卫事件为空，包装覆盖不能完全证明；MCP T1 R1任务发布后遭遇模型资源暂停，同一上下文在原截止内恢复；MCP T4 R1第二阶段发布约187秒后才发生，包含明显父级协调等待。完整时间不扣除这些等待，raw_results记录timing_comparable=false。工具截止包装只能拒绝新调用，不能强行取消在途调用或证明全局拦截。不能宣称本批次是无偏离的受控速度比较。', '',
'超时在图中以300秒右删失表示；task_s=NOT_COMPLETED，真实稍晚的模型结束声明仍在bookkeeping_end_s/timing.json。删失后中位数是描述统计，不能解释为全部任务完成时间，也不计算通用加速倍数。简单任务、复杂任务分别看全部散点，资源及编排异常必须同时披露。', '',
'## 数据、状态保护与异常恢复','']
saved=[r for r in rows if r['data_consistency'] is True];unknown=[r['trial_id'] for r in rows if r['data_consistency']=='NOT_MEASURED']
lines += [f"主要批次 {len(saved)} 轮保存产物的源字节和完整时间/波形数组一致；未测量轮次：{', '.join(unknown) or '无'}。最终非目标字段差异见逐轮 unexpected_paths，不能据最终差异为零声称操作中从未产生临时误操作。GUI T2已有临时重复局部图与恢复的日志。", '',
'程序化新Workbench重开和实际GUI重开分别记录。GUI T2原R1仅前者成功，后者未完成，不合并成完整通过。T4要求真实拒绝、拒绝后状态未变及明确修正后的恢复；缺失前后证据的轮次不计拒绝保护通过。其余T4检查以实际日志与rejected_project保存副本为依据。', '',
'## Stage3F归因与可支持的结论','',
'1. Stage3F低通过率主要来自F02两轮精确色号规格传递/规划与评分合同不一致：实际事务请求#E69F00，验收要求#D55E00；事务9/9成功，严格7/9。没有证据表明工具把正确色号执行错。完整历史上下文缺失，不能断言模型从未见过附注。',
'2. Stage4统一输入、初态、独立上下文、顺序及时间边界，改善旧实验公平性；日志、守卫覆盖、资源暂停与协调等待仍限制实际公平性，不能宣称已完全解决。',
'3. MCP在多约束T2中更容易在本次300秒预算内得到合格保存产物；严格完成仍受日志缺失影响。简单T1/T3不能据接口形式预设效率优势，应以本表时间与成功数判断。',
'4. 明显问题集中在GUI T2的长操作链/超时，以及MCP部分轮次的实验记录完整性；T4缺失证据不能解释为工作台状态保护故障。',
'5. 结构化接口对精确复合约束、显式校验拒绝和可检查配置的价值获得有限案例支持。小样本和记录偏离不足以支持普遍优越、显著加速或所有复杂科研任务可靠完成。',
'6. 本次未确证需要修改工作台核心的缺陷。已确证实验基础设施存在日志持久化、截止包装可验证性及验收缺失证据处理问题；应在下一批实验前单独改善，经用户决定后开展，不在本批中途修改核心或评分标准。',
'7. 可用于学术海报的证据包括真实指令→实际工具/GUI操作→保存重开产物，以及明确分母、失败及限制的描述结果。通用加速倍数、统计显著优越、全部失败源于GUI、真实科研物理泛化等证据不足。实验初态为明确标记的SYNTHETIC六通道基准，不能包装成真实故障诊断实验。', '',
'## 可复现材料与停止点','',
'- 任务与协议：protocol.md、tasks.json、constraints.json；原40轮及旧批次修订记录在history/与protocol_amendments.md。',
'- 冻结与环境：formal_v2/freeze.json、environment.json、supplemental_freeze.json；最终完整性审计：formal_v2/final_integrity_and_evidence_audit.json。',
'- 原始数据：raw_results.csv（含旧编排异常样本，按phase/cohort筛选）；formal_v2/raw_results.csv（主批次及补测，分cohort）；statistics.json只以原24轮作为主要分析。',
'- 每轮：formal_v2/<trial_id>/task_input.json、release.json、timing.json、execution_done.json；evidence/为实际工具与GUI原始返回、错误、截图和声明；supervision/为观察日志；acceptance/为完整配置、逐项评分、独立PNG/PDF和可复评分包。未保存轮次保留acceptance_error.json。',
'- 统计图：formal_v2/figures/strict_completion、atomic_satisfaction、all_trial_times（PNG/PDF）。',
'- 评分器正负例：scorer_validation.md、scorer_tests_pilot.log、pilot/negative_controls/；Pilot与正式数据严格分开。', '',
'模型token与费用不可可靠读取，标记NOT_MEASURED，不编造消耗。至少24个独立正式上下文，另1个用户指定补测；旧异常尝试另列。总历时受环境准备、逐轮验收、资源暂停和续跑影响，已超过约60分钟目标，不将跨暂停墙钟时间称为工具执行时间。', '',
'完成本批实验与分析后停止。海报、报告、课程正式交付和最终ZIP保持原状；下一阶段由用户审核结果后决定。']
(O/'analysis.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('analysis.md written; observed',len(rows))
