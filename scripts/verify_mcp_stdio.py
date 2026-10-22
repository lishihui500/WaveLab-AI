"""Real SDK stdio client, optionally targeting an explicitly selected GUI session.

Use --mode setup only on a disposable synthetic GUI project. Does not import data,
read source datasets or edit JSON files. Every edit goes through the MCP tool.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def verify(args):
    server = StdioServerParameters(command=sys.executable, args=["-m", "wavelab.mcp_server"], cwd=str(ROOT))
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            tools = await client.list_tools()
            async def call(name, params):
                response = await client.call_tool(name, params)
                if response.isError:
                    raise RuntimeError(str(response.content))
                return json.loads(next(c.text for c in response.content if c.type == "text"))
            result = dict(tools=[t.name for t in tools.tools])
            if not args.session:
                result["status"] = await call("get_wavelab_status", {})
            else:
                context = await call("get_figure_context", dict(session_id=args.session))
                if "error" in context:
                    raise RuntimeError(context)
                before = [p["id"] for p in context["context"]["panels"]]
                actions = []
                if args.mode == "setup":
                    assert len(before) == 1, "setup requires a fresh synthetic project with one panel"
                    channels = context["context"]["datasets"][0]["channels"]
                    actions = [dict(action="create_panel", panel_id="mcp_demo_2"), dict(action="create_panel", panel_id="mcp_demo_3")]
                    for pid in [before[0], "mcp_demo_2", "mcp_demo_3"]:
                        actions.append(dict(action="add_series", panel_id=pid, channel_id=channels[0]["channel_id"]))
                        actions.append(dict(action="update_panel", panel_id=pid, changes=dict(title_i18n=dict(zh=pid, en=pid))))
                elif args.mode == "move":
                    assert len(before) >= 3
                    actions = [dict(action="move_panel", panel_id=before[2], target_index=0)]
                elif args.mode in {"undo", "redo"}:
                    actions = [dict(action=args.mode)]
                elif args.mode == "inset_create":
                    actions = [dict(action="create_inset", panel_id=before[0], inset_id="mcp_zoom_demo",
                                    changes=dict(xlim_s=[0., .1], bounds=[.55,.5,.4,.4]))]
                elif args.mode == "inset_update":
                    actions = [dict(action="update_inset", panel_id=before[0], inset_id="mcp_zoom_demo",
                                    changes=dict(bounds=[.05,.5,.4,.4], ylim=[0.,4.], show_connectors=False))]
                elif args.mode == "inset_remove":
                    actions = [dict(action="remove_inset", panel_id=before[0], inset_id="mcp_zoom_demo")]
                if actions:
                    result["apply"] = await call("apply_plot_actions", dict(session_id=args.session,
                        expected_project_epoch=context["project_epoch"], expected_revision=context["revision"],
                        expected_fingerprint=context["fingerprint"], actions=actions, user_request="把第三幅子图移动到第一幅" if args.mode == "move" else "合成数据开发验收 " + args.mode))
                    assert "error" not in result["apply"], result["apply"]
                after = await call("get_figure_context", dict(session_id=args.session))
                result.update(before=before, after=[p["id"] for p in after["context"]["panels"]], revision=after["revision"], fingerprint=after["fingerprint"])
                result["insets"] = {p["id"]: p["insets"] for p in after["context"]["panels"]}
                if args.mode == "move":
                    assert result["after"] == [before[2], *before[:2], *before[3:]]
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if args.output:
                Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--session")
    parser.add_argument("--mode", choices=["read", "setup", "move", "undo", "redo", "inset_create", "inset_update", "inset_remove"], default="read")
    parser.add_argument("--output")
    asyncio.run(verify(parser.parse_args()))
