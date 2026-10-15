"use client";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "./auth-provider";
import { secondary } from "./group-ui";
import { APIError, api } from "@/lib/api";
import { adjustFocusEnd, chooseFocus, flushFocus, queueFocus, wantsFocus, type FocusPayload, type FocusResult } from "@/lib/focus";
import type { StudySession } from "@/lib/sessions";

export function useFocusEnabled() {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => { let alive = true; api<{focus_tracker_enabled:boolean}>("/features").then(v => { if(alive) setEnabled(v.focus_tracker_enabled); }).catch(() => {}); const timer=setInterval(()=>{api<{focus_tracker_enabled:boolean}>("/features").then(v=>{if(alive)setEnabled(v.focus_tracker_enabled);}).catch(()=>{});},15000); return () => {alive=false;clearInterval(timer);}; }, []);
  return enabled;
}
export function FocusToggle({ checked, onChange }: {checked:boolean; onChange:(value:boolean)=>void}) {
  const enabled = useFocusEnabled();
  return <div className="rounded-2xl border border-slate-200 p-5">{enabled ? <><label className="flex min-h-12 cursor-pointer items-start gap-3 font-bold"><input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className="mt-1 size-5 shrink-0 accent-emerald-600" />Focus Tracker (optional)</label><p className="mt-2 text-sm leading-relaxed text-slate-500">Uses your camera to estimate how focused you were. Video stays on this device; only a numeric summary is saved. It never changes your points or streak. You can stop at any time.</p></> : <><p className="font-bold">Focus Tracker · off</p><p className="mt-2 text-sm text-slate-500">No camera is used in this session.</p></>}</div>;
}
export function FocusFlusher() {
  const {user,token}=useAuth(); const enabled=useFocusEnabled();
  useEffect(() => { if(!enabled || !user || !token) return; const run=()=>void flushFocus(user.id,token); run(); const timer=setInterval(run,5000); window.addEventListener("focus",run); return ()=>{clearInterval(timer);window.removeEventListener("focus",run);}; }, [enabled,user,token]);
  return null;
}

export function FocusSession({ session }: {session:StudySession}) {
  const {user,token}=useAuth(); const enabled=useFocusEnabled();
  const [message,setMessage]=useState("Focus Tracker · off"); const [running,setRunning]=useState(false);
  const stopRef=useRef<()=>void>(()=>{}); const latestEnd=useRef(session.end_at);
  const pid=session.mine?.id; const active=!!pid && session.status==="running" && !session.mine?.ended_at && session.mine?.status!=="left";
  const uid=user?.id;
  useEffect(()=>{
    latestEnd.current=session.mine?.ended_at ?? session.end_at;
    if(enabled && uid && pid && token && session.mine?.ended_at) {
      adjustFocusEnd(uid,pid,Date.parse(session.mine.ended_at)); void flushFocus(uid,token);
    }
  },[enabled,uid,pid,token,session.mine?.ended_at,session.end_at]);
  useEffect(() => {
    if(!enabled || !active || !uid || !pid || !token || !wantsFocus(uid,session.id)) return;
    let disposed=false, stopped=false, stopping=false, inFlight=false, worker:Worker|undefined, stream:MediaStream|undefined;
    let timer:ReturnType<typeof setInterval>|undefined, watchdog:ReturnType<typeof setTimeout>|undefined;
    const video=document.createElement("video"); video.muted=true; video.playsInline=true;
    let paused=0, pauseStart:number|null=document.hidden?Date.now():null;
    const end=Date.parse(session.end_at); let samples=0;
    function tracksOff() { stream?.getTracks().forEach(t=>t.stop()); video.srcObject=null; }
    function pausedSeconds() { return Math.max(0,Math.floor((paused+(pauseStart?Date.now()-pauseStart:0))/1000)); }
    function save(data:{samples?:number;attentive_pct?:number;away_seconds?:number}) {
      const actualEnd=Date.parse(latestEnd.current);
      const payload:FocusPayload={opted_in:true,samples:data.samples??0,attentive_pct:data.attentive_pct??0,away_seconds:data.away_seconds??0,paused_seconds:Math.min(pausedSeconds()+Math.max(0,Math.floor((actualEnd-Date.now())/1000)),session.planned_minutes*60),sample_fps:1,tracker_version:"mp-1.1.1/minimal-v1"};
      queueFocus({uid:uid!,pid:pid!,end:actualEnd,payload}); if(Date.now()>=actualEnd) void flushFocus(uid!,token!);
    }
    function finish() { if(stopping || stopped) return; stopping=true; if(worker || stream) chooseFocus(uid!,session.id,false); tracksOff(); if(timer) clearInterval(timer); if(watchdog) clearTimeout(watchdog); if(pauseStart===null) pauseStart=Date.now(); if(worker) { worker.postMessage({type:"stop"}); watchdog=setTimeout(()=>{worker?.terminate();save({samples:0});},1500); } }
    stopRef.current=finish;
    function visibility() { if(document.hidden) { pauseStart=Date.now(); worker?.postMessage({type:"pause"}); if(!disposed) setMessage("Focus Tracker paused · tab hidden"); } else { if(pauseStart!==null) paused+=Date.now()-pauseStart; pauseStart=null; if(!disposed) setMessage("Camera on, processed on this device"); } }
    async function frame() {
      if(Date.now()>=end) {finish();return;}
      if(stopping || stopped || document.hidden || inFlight || video.readyState<2) return;
      inFlight=true;
      try { const bitmap=await createImageBitmap(video,{resizeWidth:320,resizeHeight:240}); if(stopping || stopped || document.hidden) {bitmap.close();inFlight=false;return;} worker!.postMessage({type:"frame",frame:bitmap,timestamp:performance.now()},[bitmap]); watchdog=setTimeout(()=>{ if(!disposed) {setMessage("Focus Tracker isn't available on this device");setRunning(false);} finish(); },2000); }
      catch { if(!disposed) {setMessage("Focus Tracker isn't available on this device");setRunning(false);} finish(); }
    }
    async function start() {
      try {
        if(!navigator.mediaDevices?.getUserMedia || !window.Worker || !window.createImageBitmap) throw new Error("unsupported");
        stream=await navigator.mediaDevices.getUserMedia({video:{width:320,height:240,facingMode:"user"},audio:false});
        if(disposed) {tracksOff();return;}
        video.srcObject=stream; await video.play();
        if(disposed) {tracksOff();return;}
        // Classic worker: MediaPipe's WASM loader uses importScripts. No UI-thread inference.
        worker=new Worker(new URL("../workers/focus.worker.ts",import.meta.url));
        worker.onmessage=({data})=>{
          inFlight=false; if(watchdog) clearTimeout(watchdog);
          if(data.type==="summary" || data.type==="disabled") { stopped=true; tracksOff(); if(timer) clearInterval(timer); save(data); worker?.terminate(); if(!disposed){setRunning(false);setMessage(data.message??"Focus Tracker stopped · summary saved for session end");} chooseFocus(uid!,session.id,false); return; }
          if(disposed || stopping) return;
          if(data.type==="ready") {setRunning(true);setMessage("Calibrating · 10 seconds. Sit how you'll study. Look at the screen for 5 seconds, then your notes.");timer=setInterval(()=>void frame(),1000);}
          if(data.type==="calibrating") setMessage(`Calibrating · ${data.remaining} seconds. ${data.remaining > 5 ? "Look at the screen." : "Now look at your notes."}`);
          if(data.type==="calibrated" || data.type==="sample") {samples=data.samples??samples;setMessage(`Camera on, processed on this device · ${samples} checks`);}
        };
        worker.onerror=()=>{if(!disposed){setMessage("Focus Tracker isn't available on this device");setRunning(false);}finish();};
        worker.postMessage({type:"init",origin:location.origin});
        watchdog=setTimeout(()=>{if(!disposed) setMessage("Focus Tracker isn't available on this device");finish();},30000);
      } catch { tracksOff(); chooseFocus(uid!,session.id,false); if(!disposed){setRunning(false);setMessage("Focus Tracker isn't available on this device. Camera access was denied or unsupported.");} }
    }
    void start(); document.addEventListener("visibilitychange",visibility);
    return ()=>{disposed=true;document.removeEventListener("visibilitychange",visibility);finish();setRunning(false);setMessage("Focus Tracker · off · camera off");};
  }, [enabled,active,uid,pid,token,session.id,session.end_at,session.planned_minutes]);
  return <section aria-label="Focus Tracker" className="card space-y-3 p-5"><h2 className="font-bold">Focus Tracker</h2><p aria-live="polite" className="text-sm text-slate-600">{enabled && active ? message : "Focus Tracker · off · camera off"}</p>{enabled && active && running && <button type="button" className={secondary} onClick={()=>{stopRef.current();setRunning(false);}}>Stop Focus Tracker</button>}<p className="text-xs leading-relaxed text-slate-500">Video stays on your device. Looking down at notes is allowed. Focus never changes points or streaks. Hidden tabs pause checks.</p></section>;
}

export function FocusResults({ participantId,sessionId }: {participantId:number;sessionId:number}) {
  const enabled=useFocusEnabled(); const {token}=useAuth(); const [result,setResult]=useState<FocusResult|null>(null); const [pending,setPending]=useState(false);
  useEffect(()=>{if(!enabled || !token) return;let alive=true;async function load(){try {const own=await api<Pick<FocusResult,"mine">>(`/participants/${participantId}/focus-summary`,{token:token!});if(!alive)return;setResult({mine:own.mine,comparison:null});try {const full=await api<FocusResult>(`/sessions/${sessionId}/focus-comparison`,{token:token!});if(alive){setResult(full);setPending(false);}}catch(e){if(alive && e instanceof APIError && e.status===409)setPending(true);}}catch{/* Focus is optional; study results stay available. */}}void load();const timer=setInterval(()=>void load(),15000);return()=>{alive=false;clearInterval(timer);};},[enabled,token,participantId,sessionId]);
  const mine=result?.mine;
  return <section aria-label="Your Focus Tracker result" className="card space-y-3 p-5"><h2 className="font-bold">Focus Tracker{!enabled?" · off":""}</h2>{!enabled || !mine ? <p className="text-sm text-slate-500">No focus summary for this session.</p> : <><p className="text-3xl font-extrabold text-brand-700">{mine.attentive_pct}%</p><p className="text-sm text-slate-600">You were focused {mine.attentive_pct}% of the checked time.</p>{!mine.is_valid ? <p className="text-sm text-slate-500">Not enough camera data to compare.</p> : result?.comparison ? <p className="text-sm text-slate-600">That’s {result.comparison.position} the session median of {result.comparison.median_pct}% ({result.comparison.n} valid opted-in summaries).</p> : <p className="text-sm text-slate-500">{pending?"Comparison opens 30 minutes after the session ends.":"Not enough people opted in to compare."}</p>}<p className="text-xs text-slate-500">Time away: {mine.away_seconds}s · Paused: {mine.paused_seconds}s</p></>}<p className="text-xs text-slate-500">A personal estimate only. It never changes your points or streak.</p></section>;
}
