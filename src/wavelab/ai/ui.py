"""Small assistant panel; GUI and AI always use the same Workbench instance."""
import hashlib
import json
import os
import streamlit as st

from .assistant import Assistant, figure_context
from .provider import OpenAICompatibleProvider, MockProvider
from .manual_ui import manual_panel


def setting(name, default=""):
    try:
        return st.secrets.get(name, os.environ.get(name, default))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return os.environ.get(name, default)


ASSISTANT_UI_VERSION = 2


def assistant_panel(w, *, codex_connection=None):
    with st.expander("AI 科研绘图助手", expanded=True):
        if codex_connection is not None:
            codex_connection()
        if w.spec is None:
            return
        with st.expander("其他方式：ChatGPT / API", expanded=False):
            enabled = st.checkbox("启用 AI 助手", key="ai_enabled")
            if not enabled:
                st.caption("手动协作或 API 模式在此启用，Codex 连接独立使用。")
                return
            service = st.selectbox("AI 工作模式", ["ChatGPT 手动协作", "OpenAI API", "Mock（测试）"], key="ai_service_mode")
            if service == "ChatGPT 手动协作":
                manual_panel(w)
                return
            if service == "Mock（测试）":
                st.info("固定回复测试，不调用模型。")
                st.session_state.setdefault("mock_assistant", Assistant())
                mock_assistant = st.session_state.mock_assistant
                mock_request = st.text_area("Mock 测试要求", key="mock_request")
                if st.button("运行 Mock 测试", disabled=not mock_request.strip()):
                    turn = mock_assistant.propose(w, MockProvider([{"summary": "Mock 固定澄清", "clarification": "这是一条预设测试回复，请使用手动协作模式导入绘图方案。", "actions": []}]), mock_request, consent=True, max_repairs=0)
                    st.info(turn.result.plan.clarification)
                return
            if "ai_assistant" not in st.session_state:
                st.session_state.ai_assistant = Assistant()
            assistant = st.session_state.ai_assistant
            a, b = st.columns(2)
            base = a.text_input("模型服务地址", value=setting("WAVELAB_AI_BASE_URL", "https://api.openai.com/v1"), key="ai_base_url")
            model = b.text_input("模型名称", value=setting("WAVELAB_AI_MODEL"), key="ai_model")
            mode = a.selectbox("结构化输出模式", ["json_object", "json_schema"], key="ai_response_mode")
            timeout = b.number_input("模型超时 / s", 1, 60, 45, key="ai_timeout")
            st.caption("API Key 读取自环境变量或本地 secrets；服务地址填写 API 根路径。")
            configured = bool(setting("OPENAI_API_KEY"))
            st.info(f"模型：{model or '未设置'} · API Key：{'已配置' if configured else '未配置'}")
            context = figure_context(w)
            with st.expander("查看拟发送的工程元数据"):
                st.json(context)
            st.caption("点击生成时发送指令、近期对话及所列工程元数据；不发送波形数组、源文件路径或密钥。")
            scope = hashlib.sha256(json.dumps([base, model, context["datasets"]], ensure_ascii=False).encode()).hexdigest()
            consent = st.checkbox("我确认向上述服务发送所列元数据和对话，并承担模型 API 调用费用", key="ai_consent_" + scope)
            request = st.text_area("自然语言绘图要求", key="ai_request", placeholder="仅将 B 相下桥臂设为红色虚线，其他设置不变。", max_chars=8000)
            # Provider injection exists only for local AppTest, never exposed as a production mode.
            injected = st.session_state.get("_ai_test_provider")
            if st.button("生成 AI 修改方案", disabled=not (request.strip() and consent and model and (configured or injected)), key="ai_generate"):
                try:
                    provider = injected or OpenAICompatibleProvider(model=model, api_key=setting("OPENAI_API_KEY"), base_url=base, timeout_s=timeout, response_mode=mode)
                    with st.spinner("模型规划及确定性校验中；尚未修改当前图形…"):
                        assistant.propose(w, provider, request, consent=consent)
                except ValueError as exc:
                    st.error(str(exc))
            for turn in assistant.turns[-6:]:
                with st.chat_message("user"):
                    st.write(turn.request)
                with st.chat_message("assistant"):
                    if turn.result:
                        st.write(turn.result.plan.clarification or turn.result.plan.summary)
                        st.caption(f"{'Mock 接口测试' if turn.mode == 'mock' else '真实模型调用成功'} · {turn.result.model} · {turn.calls} 次调用 · 总耗时 {turn.elapsed_s:.2f} s · Token {turn.usage or '未返回'}")
                    st.write({"pending": "等待模型", "proposed": "校验和试绘成功，等待确认应用", "applied": "绘图操作已执行", "failed": "操作失败，当前有效图形保留", "cancelled": "方案已取消", "superseded": "已被后续请求替代", "clarification": "需要补充信息，未修改图形"}.get(turn.status, turn.status))
                    if turn.error:
                        st.error(turn.error)
                    if turn.status == "proposed" and turn.proposal:
                        proposal = turn.proposal
                        if proposal.revision != w.revision:
                            st.warning("当前图形已变化，此方案过期。请重新生成。")
                        st.dataframe([{"字段": r["field"], "当前": json.dumps(r["before"], ensure_ascii=False), "目标": json.dumps(r["after"], ensure_ascii=False)} for r in proposal.changes], hide_index=True)
                        with st.expander("结构化操作与临时预览"):
                            st.json(turn.result.plan.model_dump(mode="json"))
                            st.image(proposal.preview, width="stretch")
                            for warning in proposal.warnings:
                                st.warning(warning)
                        apply, cancel = st.columns(2)
                        if apply.button("应用 AI 修改", key="ai_apply", type="primary"):
                            try:
                                assistant.apply(w, turn)
                                st.session_state.pop("exports", None)
                                st.session_state.pop("edit_error", None)
                                st.session_state.notice = "AI 方案已通过校验并应用；可使用撤销/恢复。"
                                st.rerun()
                            except ValueError as exc:
                                st.error(str(exc))
                        if cancel.button("取消 AI 方案", key="ai_cancel"):
                            assistant.cancel(turn, w)
                            st.rerun()
            st.download_button("下载 AI 评价记录（不含请求与字段值）", assistant.export_records(), file_name="ai_evaluation.json", key="ai_records")
