# WaveLab AI — Instructions for Codex

Read `WaveLab_AI_Handoff.md` first (the handoff document's actual filename). Inspect actual files before making assumptions. The later MCP task specification supersedes its original P2 scheduling for MCP.

## Drawing and development modes

- Default is drawing mode: use WaveLab MCP tools for plotting requests. Do not edit Python or project JSON to bypass the Action Executor.
- Modify source only when the user explicitly requests workbench development, fixes, or says “工作台开发模式”. An explicit next-stage development request also authorizes development.
- Query sessions/status/context before modifications. Select the exact GUI session; use current project epoch, revision and fingerprint. Never invent existing panel/channel IDs. New panel IDs must be unique and explicitly assigned in the transaction.
- Check operation results; on version conflict reread current state and regenerate from the original user intent. Do not blindly retry after an unknown connection result.
- Never guess unconfirmed physical mappings, units or unspecified fault times. Do not transform waveform samples without a user request.
- MCP modifies only through the existing validated Action Executor and Workbench undo/redo. Unsupported actions must be reported; source changes require development intent.

## Codex daily MCP workflow

- User opens a project and explicitly clicks “设为 Codex 编辑目标” in the GUI. Start with `get_edit_target`; never guess by activity, project name or port, and never use browser automation as the default locator. No binding means ask the user to select it. Re-query the target at the start of a new user instruction; reuse its session within that instruction.
- Read `get_figure_context(session_id)` once for current identity, full FigureSpec and coverage. Do not also fetch status or enumerate all sessions when this succeeds. Only query missing information. For a requested absolute time window, use `get_figure_context(session_id, window_s=[start_s,end_s])`; check finite counts and panel drawable status, not just endpoint ranges or series references. Digital tracks may carry a previous state; panel coverage follows the shared renderer semantics.
- Fetch Action schema once per compatible protocol hash. Protocol mismatch requires restarting/reconnecting GUI and MCP; no write may bypass this check. Application version is separate from protocol version.
- Construct one whitelisted Action batch with explicit unique IDs for new objects. Submit with exact session_id/project_epoch/revision/fingerprint; read back once and compare requested properties and returned identity. Conflict, rejected transaction or unknown result requires a current read before rebuilding from the user's original intent. Never blindly retry a write.
- Save only when explicitly requested. `save_project` requires current transaction identity and an existing current project under the GUI workbench's projects directory. Check `saved`, `saved_revision` and `saved_fingerprint`; unnamed/external projects need GUI save first. Saving is separate from the drawing transaction. Report failures and unperformed operations explicitly.
- Ordinary color/line/legend/panel/window/inset edits are drawing tasks: MCP only, no source edits, direct project JSON edits, or source-sample changes. Feature development, GUI fixes and MCP interface development permit source edits with relevant regression tests. See `docs/codex_mcp.md` for the single operational guide.

## Non-negotiable requirements

- Never overwrite, rename, or alter any user-provided PSCAD TXT dataset.
- CSV `Domain` is time in seconds; CSV header names may repeat. Preserve original header names and their order. A channel is identified by persisted dataset ID plus original zero-based source column index, never by its display name.
- The confirmed six-arm order in `测试集1.txt` is A-upper, A-lower, B-upper, B-lower, C-upper, C-lower. A three-channel measurement may be ABC but requires confirmation before mapping physical semantics.
- Ignore truly empty trailing rows with a warning; never silently remove partially missing rows or duplicate valid samples. Validate time monotonicity and sampling information.
- Preserve original waveform values. No implicit smoothing, interpolation, resampling, or model-fabricated curves. Preview-only decimation must not replace source data.
- Prefer Matplotlib/SciencePlots for deterministic academic figure output. AI may modify only validated structured figure commands/specs, not execute arbitrary generated code.
- App must work for imports, manual editing, save/reopen, and figure export even without an AI API key.
- Implement in reviewable, tested stages. First task is dataset inspection, parsing and pytest—not the full UI. Report tests and limitations; don't imply features are complete when unimplemented.
- Do not commit private research datasets to a public repository or transmit them to external AI/model services without user approval.

## Course project deliverables and poster workflow

- For any task involving the course assignment, poster, report, presentation materials, final submission, packaging, or related exports, **read `课程提交规范.md` before planning or editing**. For poster design or revision, also read `docs/学术海报设计规范.md`.
- Treat the course's explicit requirements as hard constraints: poster = **exactly one A1 portrait page (594 × 841 mm)** in PDF; accompanying PNG preview with **short side >= 2000 pixels**. Poster must contain project title, author name, research question, method, actual AI usage, and key results. Report is recommended to be 3–5 PDF pages. Submission includes results and a README, packed as `学号_姓名_项目名称.zip`.
- Before each relevant export, validate PDF page count and physical page dimensions programmatically, inspect PNG pixel size and visually review the *rendered* poster at full-page and detail scale. Report failures instead of declaring completion.
- For the academic poster, prioritize evidence-based **Before → real natural-language instruction → actual Codex/MCP actions → After** visual storytelling; use authentic project figures, screens, and execution records. No fabricated data, app interfaces, AI effects, or evaluation metrics.
- Course deliverable/design work is not, by itself, permission to change WaveLab application source code. Continue following the drawing/development mode rules above. Produce presentation assets separately from original PSCAD inputs and working projects.
- Do not overwrite the original `AGENTS.md` rules or silently change these standing constraints. If a request conflicts with the instructor's requirements, flag the conflict before proceeding. If a referenced specification file is missing, report it instead of guessing the rules.

## Task-scoped file navigation

- Preserve all rules above. Read Handoff first, then only the specifications and files relevant to the current task; its initial implementation-status text is historical.
- Plotting: query WaveLab MCP status/context and the selected project. Persisted projects are under `.wavelab/projects/`; protect each project's data directory and source identities. Do not scan runtime secrets.
- Development: search `src/wavelab/`, relevant `tests/`, `scripts/`, `app.py`, and dependency/configuration files. `test/fixtures/` holds protected real input data; it is distinct from `tests/`.
- Course work: read course specifications first. Current deliverables are in `deliverables/course_2026/current/`; report source is `项目/materials/报告.tex`. Active portrait build scripts remain in `.poster_portrait_build/` and include writes: do not execute them merely to inspect existing deliverables.
- The official ZIP remains at the root because Windows blocked its move. See `docs/maintenance/cleanup_path_mapping.json` and the execution report for actual locations and incomplete work.
- History: `reports/` includes live test baselines; `submission_draft/` still provides source evidence; `poster_redesign_20261020/` is historical landscape output. No archive migration has been approved or executed.
- Default text searches must be limited to task-relevant directories. Exclude `.venv/`, caches, `.chart-data-*`, build outputs, delivery source duplicates and historical experiment trees from routine searches. Enter a specific historical/build directory only when needed. Never load the entire historical project into daily context.
- Maintenance: read `docs/maintenance/repository_cleanup_execution.md` before continuing cleanup. The original deletion manifest uses pre-migration paths; do not blindly replay it after migration.
