"""Real stdio acceptance for a selected synthetic GUI project with V source units."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(args):
    root=Path(__file__).resolve().parents[1]
    server=StdioServerParameters(command=sys.executable,args=["-m","wavelab.mcp_server"],cwd=str(root))
    async with stdio_client(server) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            async def call(name,params):
                print("Calling " + name,file=sys.stderr,flush=True)
                result=await asyncio.wait_for(client.call_tool(name,params),timeout=45)
                assert not result.isError,result
                data=json.loads(next(c.text for c in result.content if c.type=="text"))
                assert "error" not in data,data
                print("Received " + name,file=sys.stderr,flush=True)
                return data
            registry=await call("get_quantity_presets",{})
            schema=await call("get_plot_action_schema",{})
            assert "set_display_unit" in schema["change_fields"]
            context=await call("get_figure_context",dict(session_id=args.session))
            source=context["context"]["datasets"]
            panel=context["context"]["panels"][0]
            assert source[0]["channels"][0]["unit"]=="V","use the V-source synthetic acceptance project"
            async def apply(actions):
                nonlocal context
                result=await call("apply_plot_actions",dict(session_id=args.session,
                    expected_revision=context["revision"],expected_project_epoch=context["project_epoch"],
                    expected_fingerprint=context["fingerprint"],actions=actions,
                    user_request="单位预设开发验收：电压源单位V，显示kV并添加0到0.1s局部图；再V/kV切换"))
                context=await call("get_figure_context",dict(session_id=args.session))
                assert context["context"]["datasets"]==source
                return dict(revision=context["revision"],fingerprint=context["fingerprint"],panel=context["context"]["panels"][0],result=result["result"])
            steps=[]
            initial=[dict(action="set_axis_quantity",panel_id=panel["id"],changes=dict(preset_id="voltage",unit="kV"))]
            if not any(i["id"]=="quantity_zoom" for i in panel["insets"]):
                initial.append(dict(action="create_inset",panel_id=panel["id"],inset_id="quantity_zoom",changes=dict(xlim_s=[0,.1],ylim=[0.,30.])))
            steps.append(await apply(initial))
            steps.append(await apply([dict(action="set_display_unit",panel_id=panel["id"],changes=dict(unit="V"))]))
            assert context["context"]["panels"][0]["insets"][0]["ylim"]==[0.,30000.]
            steps.append(await apply([dict(action="set_display_unit",panel_id=panel["id"],changes=dict(unit="kV"))]))
            assert context["context"]["panels"][0]["insets"][0]["ylim"]==[0.,30.]
            evidence=dict(registry_count=len(registry["quantities"]),steps=steps,source_metadata_unchanged=True)
            path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(dict(registry_count=len(registry["quantities"]),revisions=[s["revision"] for s in steps],source_metadata_unchanged=True)))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--session",required=True)
    parser.add_argument("--output",default="reports/quantity_presets/stdio.json")
    asyncio.run(main(parser.parse_args()))
