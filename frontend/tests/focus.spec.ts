import { execFileSync } from "node:child_process";
import { expect, test, type Page, type APIRequestContext } from "@playwright/test";
import { FocusCounts, headOK, headPose } from "../src/lib/focus-math";

test.use({ serviceWorkers: "block" });
test.skip(process.env.FOCUS_TRACKER_ENABLED !== "true", "Run make test-focus for the flagged tracker.");

async function learner(page:Page, request:APIRequestContext) {
  const email=`focus-${crypto.randomUUID()}@example.com`, password="focus-browser-password";
  await request.post("/api/v1/auth/register",{data:{email,password,display_name:"Focus Learner",level:"SS2",audience_band:"secondary",guardian_consent:true}});
  const token=(await(await request.post("/api/v1/auth/jwt/login",{form:{username:email,password}})).json()).access_token as string;
  await page.goto("/");await page.evaluate(token=>sessionStorage.setItem("studyflow-token",token),token);await page.goto("/study");
  await page.getByLabel("What are you studying?",{exact:true}).fill("Mole concept");await page.getByLabel("Subject",{exact:true}).fill("Chemistry");
  return {token,headers:{Authorization:`Bearer ${token}`}};
}
async function camera(page:Page, mockWorker=true) {
  await page.addInitScript(({mockWorker})=>{
    const state={calls:0,stops:0,frames:0,slow:false}; Object.assign(window,{focusTest:state});
    const canvas=document.createElement("canvas");canvas.width=320;canvas.height=240;
    const bitmap=window.createImageBitmap.bind(window);
    Object.defineProperty(navigator,"mediaDevices",{configurable:true,value:{getUserMedia:async()=>{
      state.calls++;const stream=new MediaStream();Object.defineProperty(stream,"getTracks",{value:()=>[{stop:()=>state.stops++}]});return stream;
    }}});
    HTMLMediaElement.prototype.play=async()=>{};
    Object.defineProperty(HTMLMediaElement.prototype,"readyState",{configurable:true,get:()=>2});
    window.createImageBitmap=(()=>bitmap(canvas)) as typeof createImageBitmap;
    if(mockWorker) {
      class MockWorker {
        onmessage:((event:{data:object})=>void)|null=null; onerror=null; samples=0;
        constructor(){}
        postMessage(data:{type:string}) {
          const emit=(data:object)=>queueMicrotask(()=>this.onmessage?.({data}));
          if(data.type==="init")emit({type:"ready"});
          if(data.type==="frame" && state.slow) {emit({type:"disabled",message:"Focus Tracker isn't available on this device",samples:0,attentive_pct:0,away_seconds:0});return;}
          if(data.type==="frame") {state.frames++; if(state.frames<10)emit({type:"calibrating",remaining:10-state.frames});else if(state.frames===10)emit({type:"calibrated"});else emit({type:"sample",samples:++this.samples});}
          if(data.type==="stop")emit({type:"summary",samples:this.samples,attentive_pct:100,away_seconds:0});
        }
        terminate(){}
      }
      window.Worker=MockWorker as unknown as typeof Worker;
    }
  },{mockWorker});
}

test("minimal math respects notes, forgiveness, away and pause boundaries",()=>{
  expect(headOK(30,-45,{yaw:0,pitch:0})).toBeTruthy();expect(headOK(-30,20,{yaw:0,pitch:0})).toBeTruthy();expect(headOK(31,0,{yaw:0,pitch:0})).toBeFalsy();
  const degrees=40*Math.PI/180;
  const matrix=[1,0,0,0,0,Math.cos(degrees),Math.sin(degrees),0,0,-Math.sin(degrees),Math.cos(degrees),0,0,0,0,1];
  expect(headPose(matrix).pitch).toBeCloseTo(-40);
  expect(headOK(headPose(matrix).yaw,headPose(matrix).pitch,{yaw:0,pitch:0})).toBeTruthy();
  const upward=[...matrix];upward[6]*=-1;upward[9]*=-1;
  expect(headPose(upward).pitch).toBeCloseTo(40);
  expect(headOK(headPose(upward).yaw,headPose(upward).pitch,{yaw:0,pitch:0})).toBeFalsy();
  for(const [seconds,expected,away] of [[5,100,0],[6,0,0],[20,100,0],[21,0,21]]) {
    const counts=new FocusCounts();for(let i=0;i<seconds;i++)counts.add(seconds<10, false);
    expect(counts.summary()).toEqual({samples:seconds,attentive_pct:expected,away_seconds:away});
  }
  const counts=new FocusCounts();for(let i=0;i<20;i++)counts.add(false,false);counts.flush();for(let i=0;i<20;i++)counts.add(false,false);
  expect(counts.summary()).toEqual({samples:40,attentive_pct:100,away_seconds:0});
});

test("opt-in mocked worker pauses, stops camera and posts numeric summary only",async({page,request},testInfo)=>{
  await camera(page);await page.clock.install();const {headers}=await learner(page,request);
  const toggle=page.getByRole("checkbox",{name:"Focus Tracker (optional)",exact:true});await expect(toggle).not.toBeChecked();
  expect(await page.evaluate(()=> (window as unknown as {focusTest:{calls:number}}).focusTest.calls)).toBe(0);
  await toggle.check();await page.getByRole("button",{name:"Start solo session",exact:true}).click();
  await expect(page.getByRole("region",{name:"Focus Tracker",exact:true})).toContainText("Calibrating");
  const sid=Number(new URL(page.url()).pathname.split("/").at(-1));
  for(let i=0;i<13;i++)await page.clock.runFor(1000);
  const tracker=page.getByRole("region",{name:"Focus Tracker",exact:true});await expect(tracker).toContainText("3 checks");
  await page.evaluate(()=>{Object.defineProperty(document,"hidden",{configurable:true,get:()=>true});document.dispatchEvent(new Event("visibilitychange"));});
  await expect(tracker).toContainText("paused");await page.clock.runFor(3000);
  expect(await page.evaluate(()=>(window as unknown as {focusTest:{frames:number}}).focusTest.frames)).toBe(13);
  await page.evaluate(()=>{Object.defineProperty(document,"hidden",{configurable:true,get:()=>false});document.dispatchEvent(new Event("visibilitychange"));});
  await page.clock.runFor(1000);await expect(tracker).toContainText("4 checks");
  await page.getByRole("button",{name:"Stop Focus Tracker",exact:true}).click();await expect(tracker).toContainText("summary saved");
  expect(await page.evaluate(()=>(window as unknown as {focusTest:{stops:number}}).focusTest.stops)).toBeGreaterThan(0);
  const pending=await page.evaluate(()=>{const key=Object.keys(sessionStorage).find(k=>k.startsWith("studyflow-focus-pending:"))!;return JSON.parse(sessionStorage.getItem(key)!);});
  expect(pending.payload.samples).toBe(4);expect(pending.payload.paused_seconds).toBeGreaterThan(3);
  // Listen before changing persisted time: presence can announce the end immediately.
  const post=page.waitForRequest(r=>r.url().endsWith(`/participants/${pending.pid}/focus-summary`)&&r.method()==="POST");
  // Advance only this disposable fixture. No production timer/debug endpoint is added.
  if(!process.env.DATABASE_URL?.startsWith("sqlite+aiosqlite:////tmp/studyflow-"))throw new Error("Disposable fixture required");
  execFileSync("../backend/.venv/bin/python",["-c",`
from datetime import timedelta
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.database import database_url, configure_sqlite
from app.db.types import utc_now
from app.models import StudySession, SessionParticipant
engine=create_engine(database_url(get_settings().database_url).replace('sqlite+aiosqlite:', 'sqlite:'))
configure_sqlite(engine)
with Session(engine) as db:
    db.connection(execution_options={"sqlite_transaction_mode":"IMMEDIATE"})
    s=db.get(StudySession,int(sys.argv[1]));p=db.get(SessionParticipant,int(sys.argv[2]))
    s.end_at=utc_now()-timedelta(seconds=1);s.started_at=s.end_at-timedelta(minutes=25);s.scheduled_at=s.started_at;s.status='ended'
    p.joined_at=s.started_at;p.ended_at=s.end_at;p.active_seconds=1500;p.status='joined';p.quiz_status='unavailable'
    db.commit()
engine.dispose()
`,String(sid),String(pending.pid)],{env:{...process.env,PYTHONPATH:"../backend"}});
  await request.get(`/api/v1/sessions/${sid}`,{headers});
  // Reload observes the real earlier end and moves the stopped tracker draft to that end.
  await page.reload();
  const sent=(await post).postDataJSON();expect(Object.keys(sent).sort()).toEqual(["opted_in","attentive_pct","away_seconds","samples","paused_seconds","sample_fps","tracker_version"].sort());
  await expect.poll(async()=> (await(await request.get(`/api/v1/participants/${pending.pid}/focus-summary`,{headers})).json()).mine?.samples).toBe(4);
  await page.goto(`/participants/${pending.pid}/quiz`);await expect(page.getByRole("region",{name:"Your Focus Tracker result",exact:true})).toContainText("Not enough camera data");
  await page.screenshot({path:testInfo.outputPath("focus-partial.png")});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});

test("seeded live result shows own score and anonymous closed-window median",async({page,request},testInfo)=>{
  const token=(await(await request.post("/api/v1/auth/jwt/login",{form:{username:"ada@demo.studyflow.example.com",password:"StudyFlow-demo-2026!"}})).json()).access_token as string;
  const headers={Authorization:`Bearer ${token}`};const data=await(await request.get("/api/v1/users/me/dashboard",{headers})).json();
  let pid:number|undefined;
  for(const p of data.recent){const response=await request.get(`/api/v1/sessions/${p.session_id}/focus-comparison`,{headers});if(response.ok()&&(await response.json()).comparison){pid=p.participant_id;break;}}
  expect(pid).toBeTruthy();await page.goto("/");await page.evaluate(token=>sessionStorage.setItem("studyflow-token",token),token);await page.goto(`/participants/${pid}/quiz`);
  const card=page.getByRole("region",{name:"Your Focus Tracker result",exact:true});await expect(card).toContainText("90%");await expect(card).toContainText("above the session median of 80% (3 valid opted-in summaries)");
  await expect(card).not.toContainText("Tunde");await expect(card).not.toContainText("Zainab");await card.screenshot({path:testInfo.outputPath("focus-comparison.png")});
});

test("real worker loads local model and processes a synthetic blank frame",async({page,request})=>{
  await camera(page,false);await learner(page,request);const assets:string[]=[];page.on("response",r=>{if(r.url().includes("/focus-assets/")){expect(r.status()).toBe(200);assets.push(r.url());}});
  await page.getByRole("checkbox",{name:"Focus Tracker (optional)",exact:true}).check();await page.getByRole("button",{name:"Start solo session",exact:true}).click();
  const tracker=page.getByRole("region",{name:"Focus Tracker",exact:true});
  await expect(tracker).toContainText("Calibrating",{timeout:30000});
  await expect(tracker).toContainText("We can't see your face clearly",{timeout:25000});
  expect(assets.some(url=>url.endsWith(".wasm"))).toBeTruthy();expect(assets.some(url=>url.endsWith(".task"))).toBeTruthy();expect(assets.every(url=>url.startsWith(new URL(page.url()).origin))).toBeTruthy();
});

test("runtime kill switch stops the camera",async({page,request})=>{
  await camera(page);await page.clock.install();await learner(page,request);
  await page.getByRole("checkbox",{name:"Focus Tracker (optional)",exact:true}).check();await page.getByRole("button",{name:"Start solo session",exact:true}).click();
  const tracker=page.getByRole("region",{name:"Focus Tracker",exact:true});await expect(tracker).toContainText("Calibrating");
  await page.route("**/api/v1/features",route=>route.fulfill({json:{focus_tracker_enabled:false}}));
  await page.clock.runFor(15000);await expect(tracker).toContainText("Focus Tracker · off");
  expect(await page.evaluate(()=>(window as unknown as {focusTest:{stops:number}}).focusTest.stops)).toBeGreaterThan(0);
  await page.unroute("**/api/v1/features");await page.clock.runFor(15000);
  await expect(tracker).toContainText("camera off");await expect(page.getByRole("button",{name:"Stop Focus Tracker",exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>(window as unknown as {focusTest:{calls:number}}).focusTest.calls)).toBe(1);
});

test("feature disabled requests no camera or model",async({page,request})=>{
  await camera(page);const assets:string[]=[];page.on("request",r=>{if(r.url().includes("focus-assets"))assets.push(r.url());});
  await page.route("**/api/v1/features",route=>route.fulfill({json:{focus_tracker_enabled:false}}));await learner(page,request);
  await expect(page.getByText("Focus Tracker · off",{exact:true})).toBeVisible();await expect(page.getByRole("checkbox",{name:"Focus Tracker (optional)",exact:true})).toHaveCount(0);
  await page.getByRole("button",{name:"Start solo session",exact:true}).click();await expect(page.getByRole("region",{name:"Focus Tracker",exact:true})).toContainText("off");
  expect(await page.evaluate(()=>(window as unknown as {focusTest:{calls:number}}).focusTest.calls)).toBe(0);expect(assets).toEqual([]);
});


test("slow-worker disable stops tracks and retains a partial numeric summary",async({page,request})=>{
  await camera(page);await page.clock.install();await learner(page,request);
  await page.evaluate(()=>{(window as unknown as {focusTest:{slow:boolean}}).focusTest.slow=true;});
  await page.getByRole("checkbox",{name:"Focus Tracker (optional)",exact:true}).check();await page.getByRole("button",{name:"Start solo session",exact:true}).click();
  const tracker=page.getByRole("region",{name:"Focus Tracker",exact:true});await expect(tracker).toContainText("Calibrating");await page.clock.runFor(1000);
  await expect(tracker).toContainText("isn't available on this device");expect(await page.evaluate(()=>(window as unknown as {focusTest:{stops:number}}).focusTest.stops)).toBeGreaterThan(0);
  await expect(page.getByRole("button",{name:"Stop Focus Tracker",exact:true})).toHaveCount(0);
});
