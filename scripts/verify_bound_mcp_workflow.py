"""Read the explicit GUI target; --apply performs the user-authorized u acceptance edit.

No browser, raw data transfer, direct project writes, or implicit save.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main(apply=False):
    record = dict(transport="MCP SDK stdio -> HTTP bridge -> live GUI thread", browser_automation=False)
    async with stdio_client(StdioServerParameters(command=sys.executable, args=["-m", "wavelab.mcp_server"], cwd=str(ROOT))) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            async def call(name, arguments):
                response = await client.call_tool(name, arguments)
                if response.isError:
                    raise RuntimeError(str(response.content))
                result = json.loads(next(c.text for c in response.content if c.type == "text"))
                assert "error" not in result, result
                return result
            record["target"] = await call("get_edit_target", {})
            sid = record["target"]["target"]["session_id"]
            before = record["before"] = await call("get_figure_context", dict(session_id=sid))
            assert before["project_epoch"] == record["target"]["target"]["project_epoch"]
            if apply:
                schema = await call("get_plot_action_schema", {})
                assert schema["protocol"] == before["protocol"]
                channels = [c for d in before["context"]["datasets"] for c in d["channels"] if c["display_name"] == "u"]
                assert len(channels) == 1, "ambiguous/missing u; no write"
                cid = channels[0]["channel_id"]
                actions = [dict(action="set_channel_properties", channel_id=cid, changes=dict(display_name="电压"))]
                placements = [p for p in before["context"]["panels"] if any(s["channel_id"] == cid for s in p["series"])]
                assert placements, "u has no series; no write"
                for panel in placements:
                    actions.append(dict(action="update_series", panel_id=panel["id"], channel_id=cid,
                                        changes=dict(color="#FF0000", linestyle="--")))
                record["actions"] = actions
                record["apply"] = await call("apply_plot_actions", dict(session_id=sid,
                    expected_project_epoch=before["project_epoch"], expected_revision=before["revision"],
                    expected_fingerprint=before["fingerprint"], actions=actions,
                    user_request="我希望把u的图例改成电压，设成红色虚线。"))
                after = record["after"] = await call("get_figure_context", dict(session_id=sid))
                assert after["fingerprint"] == record["apply"]["fingerprint"]
                assert after["revision"] == before["revision"] + 1
                c = next(c for d in after["context"]["datasets"] for c in d["channels"] if c["channel_id"] == cid)
                assert c["display_name"] == "电压" and c["unit"] == channels[0]["unit"]
                for p in after["context"]["panels"]:
                    for s in p["series"]:
                        if s["channel_id"] == cid:
                            assert s["color"] == "#FF0000" and s["linestyle"] == "--"
                assert record["apply"]["result"]["samples_unchanged"]
                record["verified"] = True
                record["save_performed"] = False
    destination = ROOT / "reports" / "mcp_workflow_20261022" / ("live_acceptance.json" if apply else "live_read.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(verified=record.get("verified"), session_id=sid,
                         before_revision=before["revision"], after_revision=record.get("after", {}).get("revision"),
                         save_performed=False, stages=record.get("apply", {}).get("diagnostics")), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
