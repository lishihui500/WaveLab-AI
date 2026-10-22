"""Three-step manual collaboration UI; clipboard writes require an explicit click."""
from html import escape
import json

import streamlit as st
import streamlit.components.v1 as components

from .manual import ManualExchange


def clipboard(prompt):
    # Escape HTML data, never interpolate user/model text into JavaScript.
    components.html('''<!doctype html><html lang="zh"><meta charset="utf-8">
<style>body{font:14px sans-serif;margin:0}textarea{width:98%;height:125px;box-sizing:border-box}
button{padding:7px;margin-bottom:6px}p{margin:5px 0}</style>
<button id="copy">一键复制请求</button><span id="status" role="status" aria-live="polite"></span>
<textarea id="request" readonly aria-label="请求内容（可全选手动复制）">''' + escape(prompt) + '''</textarea>
<script>document.getElementById('copy').onclick=async()=>{
const box=document.getElementById('request'),status=document.getElementById('status');
try{await navigator.clipboard.writeText(box.value);status.textContent=' 已复制请求';}
catch(e){box.focus();box.select();
try{if(!document.execCommand('copy'))throw new Error();status.textContent=' 已复制请求（兼容模式）';}
catch(e){status.textContent=' 自动复制失败：内容已选中，请按 Ctrl+C 手动复制';}}
};</script></html>''', height=200)


def manual_panel(w):
    if "manual_exchange" not in st.session_state:
        st.session_state.manual_exchange = ManualExchange()
    exchange = st.session_state.manual_exchange
    # Streamlit removes widget keys while another mode is shown. Retain drafts
    # separately so mode switches and disabling the assistant do not discard them.
    for key in ("manual_request", "manual_json"):
        if key not in st.session_state:
            st.session_state[key] = st.session_state.get(key + "_draft", "")
    def keep_draft(key):
        st.session_state[key + "_draft"] = st.session_state[key]
    st.caption("复制请求到 ChatGPT，再粘贴最终 JSON 方案。请先检查要发送的内容。")
    st.markdown("**步骤 1：生成请求**")
    request = st.text_area("自然语言绘图要求", key="manual_request", max_chars=8000,
                           on_change=keep_draft, args=("manual_request",),
                           placeholder="仅将 B 相下桥臂设为红色虚线，其余参数保持不变。")
    scope = st.selectbox("请求上下文", ["auto", "figure", "all"], format_func=lambda v: {"auto": "自动（明确局部任务精简，否则完整元数据）", "figure": "当前图形（需要其他通道时补充上下文）", "all": "全部数据集元数据"}[v])
    if st.button("生成 ChatGPT 请求", key="manual_generate", disabled=not request.strip()):
        try:
            exchange.generate(w, request, scope=scope, panel_id=st.session_state.get("target_panel"))
            st.session_state.pop("manual_error", None)
            st.session_state["manual_confirmation"] = ""
        except ValueError as exc:
            st.session_state.manual_error = str(exc)
    if exchange.snapshot:
        st.caption(f"请求快照：{exchange.snapshot.request_id} · revision {exchange.snapshot.revision}")
        if not exchange.current(w) and exchange.status not in {"applied", "cancelled"}:
            st.info("工程已修改，旧快照已过期；请重新生成快照和最终方案。")
        with st.expander("查看即将复制的内容", expanded=False):
            clipboard(exchange.snapshot.prompt)
            st.code(exchange.snapshot.prompt, language="text")
            st.caption("自动复制失败时，选中上方只读文本框并按 Ctrl+A、Ctrl+C；也可下载文本后复制。")
            st.download_button("下载请求文本", exchange.snapshot.prompt, file_name="wavelab_request.txt", key="manual_download")
    st.caption("需要澄清时，在同一 ChatGPT 对话中回答，最后只导入最终 JSON。")
    st.markdown("**步骤 2：导入 AI 方案**")
    source = st.selectbox("方案来源（自行标记，不代表已验证）", ["未核实来源", "脚本构造 JSON", "Mock JSON", "用户从真实 ChatGPT 获取"], key="manual_source")
    sources = {"未核实来源": "manual_unverified", "脚本构造 JSON": "scripted_json", "Mock JSON": "mock", "用户从真实 ChatGPT 获取": "user_chatgpt"}
    raw = st.text_area("粘贴 ChatGPT 返回结果", key="manual_json", height=200, max_chars=250000,
                       on_change=keep_draft, args=("manual_json",))
    confirmation = st.text_area("后续确认原话（仅新增事件秒值或源单位证据时填写）", max_chars=8000, key="manual_confirmation")
    if st.button("解析并验证方案", key="manual_validate", disabled=not raw.strip()):
        try:
            exchange.validate(w, raw, source=sources[source], confirmation=confirmation)
            st.session_state.pop("manual_error", None)
        except ValueError as exc:
            st.session_state.manual_error = str(exc)
    if error := st.session_state.get("manual_error"):
        st.error(error)
    if exchange.status == "clarification" and exchange.response:
        st.info("旧协议澄清回复：请直接回同一 ChatGPT 对话回答，无需重新导出快照。" + exchange.response.plan.clarification)
    st.markdown("**步骤 3：预览并应用**")
    if exchange.status == "proposed" and exchange.proposal:
        p = exchange.proposal
        if (raw != exchange.validated_raw or confirmation != exchange.confirmation):
            st.warning("粘贴内容已变化，请重新解析并验证后再应用。以下为上次通过的候选方案。")
        st.write(p.plan.summary)
        st.caption("本地校验及试绘已通过，尚未应用。请核对每个差异和图像。")
        st.dataframe([{"字段": r["field"], "原值": json.dumps(r["before"], ensure_ascii=False),
                       "新值": json.dumps(r["after"], ensure_ascii=False)} for r in p.changes], hide_index=True)
        st.image(p.preview, width="stretch")
        for warning in p.warnings:
            st.warning(warning)
        a, b = st.columns(2)
        if a.button("确认应用协作方案", key="manual_apply", type="primary", disabled=not exchange.bound(w) or (raw != exchange.validated_raw or confirmation != exchange.confirmation)):
            try:
                result = exchange.apply(w)
                st.session_state.pop("exports", None)
                st.session_state.pop("edit_error", None)
                st.session_state.notice = "协作方案已应用；可撤销、恢复和保存。下一轮请生成最新请求。"
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if b.button("取消协作方案", key="manual_cancel"):
            exchange.cancel()
            st.rerun()
    elif exchange.status == "applied":
        st.success("上次协作方案已确认应用；当前状态以画布为准。下一轮请重新生成请求。")
    elif exchange.status == "cancelled":
        st.info("方案已取消，图形未修改。")
    st.download_button("下载手动协作验证记录", json.dumps(exchange.records, ensure_ascii=False, indent=2),
                       file_name="manual_evaluation.json", key="manual_records")
