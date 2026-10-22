// Isolated code-level timer tests. No browser, network, global input monitoring or human measurement.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const html=fs.readFileSync(path.join(root,'reports/stage_03F/manual_timer.html'),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const defaults={task:'F01',method:'manual_gui',repeat:'1',experience:'TOOL SELF TEST',project:'synthetic self-test only',result:'PASS',operations:'',retries:'',notes:'self-test,"quoted"'};
const elements=new Map();
function node(){return {value:'',disabled:false,textContent:'',children:[],appendChild(child){this.children.push(child);},click(){if(this.href)downloads.push(this.href);}};}
for(const id of ['task','method','repeat','experience','project','result','operations','retries','notes','start','stop','clock','rows','json','csv'])elements.set(id,Object.assign(node(),{value:defaults[id]??''}));
let now=0;const blobs=new Map(),downloads=[];
const context={document:{getElementById:id=>elements.get(id),createElement:()=>node()},performance:{now:()=>now},Date,Blob,URL:{createObjectURL(blob){const id='self-test:'+blobs.size;blobs.set(id,blob);return id;},revokeObjectURL(){}},setInterval:()=>1,clearInterval(){},setTimeout(){}};
vm.runInNewContext(script,context,{timeout:1000});
elements.get('start').onclick();assert.equal(elements.get('start').disabled,true);assert.equal(elements.get('stop').disabled,false);
now=1250;elements.get('stop').onclick();assert.equal(elements.get('clock').textContent,'1.250 s');assert.equal(elements.get('rows').children.length,1);
elements.get('stop').onclick();assert.equal(elements.get('rows').children.length,1);
elements.get('json').onclick();const json=JSON.parse(await blobs.get(downloads.at(-1)).text());
assert.equal(json.records[0].drawing_and_save_seconds,1.25);assert.equal(json.records[0].method,'manual_gui');assert.equal(json.records[0].operation_count,null);assert.equal(json.records[0].automatic_interaction_tracking,false);
elements.get('csv').onclick();const csv=await blobs.get(downloads.at(-1)).text();assert.ok(csv.includes('self-test,""quoted""'));assert.ok(csv.includes('drawing_and_save_seconds'));
const result={passed:true,kind:'isolated deterministic JavaScript code test, NOT human benchmark',checks:['start/stop button state','elapsed duration from controlled performance clock','duplicate stop ignored','JSON export','null optional operation count','no automatic interaction tracking','CSV quote escaping'],browser_ui_test:'BLOCKED: browser tool disallows file URL protocol; no URL-policy workaround attempted',downloads_written:false};
fs.writeFileSync(path.join(root,'reports/stage_03F/tool_checks/timer_tool_test.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
