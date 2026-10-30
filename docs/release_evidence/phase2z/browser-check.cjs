const {chromium}=require('/Users/urjasoft/.npm/_npx/31e32ef8478fbf80/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const base=process.argv[2],out=process.argv[3];fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'/Users/urjasoft/Library/Caches/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-mac-arm64/chrome-headless-shell',args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
 const records={};
 const page=await browser.newPage({viewport:{width:1920,height:1080},reducedMotion:'reduce'});const errors=[],checks=[],endpoints=[];page.on('pageerror',e=>errors.push(String(e))); page.on('response',async r=>{if(r.url().includes('/api/demo/executions/')){try{const d=await r.json();if(d.scenario_data)records[d.scenario_id]=d.scenario_data}catch{}}});
 const assert=(ok,msg)=>{if(!ok)throw Error(msg)};
 for(const path of ['/health','/demo','/console','/safety-lab','/architecture']){let r=await page.request.get(base+path);assert(r.ok(),path);endpoints.push({path,status:r.status()});}
 await page.goto(base+'/demo');
 const plan={safe:[['observe','UNVERIFIED','OPEN'],['execution','UNVERIFIED','CLOSED'],['verification','VERIFIED','CLOSED']],denied:[['policy','DENIED','OPEN'],['authorization','DENIED','OPEN'],['execution','DENIED','OPEN']],toctou:[['world_change','UNVERIFIED','OPEN'],['revalidation','BLOCKED','OPEN'],['execution','BLOCKED','OPEN']],recovery:[['execution','UNVERIFIED','OPEN'],['verification','VERIFICATION_FAILED','OPEN'],['recovery','UNVERIFIED','CLOSED']],telemetry:[['observe','UNVERIFIED','OPEN'],['execution','UNVERIFIED','CLOSED'],['verification','VERIFIED','CLOSED']],evidence:[['observe','UNVERIFIED','OPEN'],['execution','UNVERIFIED','CLOSED'],['verification','VERIFIED','CLOSED']]};
 for(const [scene,steps] of Object.entries(plan)){
  let fixture;
  await page.getByTestId('timeline-step-'+scene).click();await page.getByTestId('plant-source').waitFor();for(let i=0;i<100&&!records[scene];i++)await new Promise(r=>setTimeout(r,100)); fixture=records[scene];assert(fixture,'actual execution record '+scene);
  assert((await page.getByTestId('stage-item-verification').innerText()).includes('PENDING'),'future stage');
  for(const [stage,status,valve] of steps){
   await page.getByTestId('stage-item-'+stage).click();await page.waitForFunction(s=>document.querySelector('[data-testid=director-status-badge]')?.textContent.includes('STATUS: '+s),status);
   const plant=page.locator('.webgl-plant-container');const state=JSON.parse(await plant.getAttribute('data-source-state'));assert(state.valve_b_state===valve,scene+' valve');if(!fixture.digital_twin_snapshots.some(s=>JSON.stringify(s)===JSON.stringify(state))){const path=await page.getByTestId('plant-source').innerText();const w=path.includes('execution_result.observed_state')?fixture.execution_result?.observed_state:path.includes('post_state')?fixture.post_state:path.includes('pre_state')?(fixture.pre_state??fixture.decision_record?.world_state_snapshot):null;assert(w&&state.valve_b_state===w.valves?.valve_b&&state.cooling_state===w.cooling&&state.human_zone===w.human_zone&&state.world_version===(w.version??w.world_version)&&state.pump_state===w.pumps?.pump_p1&&state.leak_active===(w.leak?.active??w.leak_active),'recorded world projection '+scene+'/'+stage);}
   const expected=valve==='OPEN'?0:Math.PI/2;await page.waitForFunction(a=>Math.abs(Number(document.querySelector('.webgl-plant-container')?.dataset.renderedValveRadians)-a)<1e-6,expected);
   assert(await page.locator('.webgl-canvas').count()===1,'WebGL');assert((await page.getByTestId('director-mode-badge').innerText()).includes('REPLAY'),'public REPLAY');
   for(const sel of ['.stage-compact-header','.webgl-plant-container','.webgl-hud-overlay']){const b=await page.locator(sel).boundingBox();assert(b&&b.x>=0&&b.y>=0&&b.x+b.width<=1920&&b.y+b.height<=1080,'framing '+sel);}
   if(scene==='denied'&&stage==='authorization')assert((await page.locator('.ticket-status-badge').innerText())==='NOT_ISSUED','zero ticket');
   if(scene==='recovery'&&stage==='recovery')assert((await page.getByTestId('stage-expanded-content').innerText()).includes('FINAL INDEPENDENT VERIFICATION NOT RECORDED'),'recovery disclosure');
   checks.push({scene,stage,status,valve,snapshot:state,source:await page.getByTestId('plant-source').innerText(),mesh_radians:await plant.getAttribute('data-rendered-valve-radians')});
  }
  await page.screenshot({path:out+'/'+scene+'.png'});
 }
 assert(!errors.length,'page errors');fs.writeFileSync(out+'/browser.json',JSON.stringify({base,viewport:[1920,1080],endpoints,checks,page_errors:errors},null,2));await browser.close();console.log(checks.length+' actual source/mesh/status checks passed');
})().catch(e=>{console.error(e);process.exit(1)});
