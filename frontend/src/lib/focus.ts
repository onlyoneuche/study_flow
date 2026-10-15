import { APIError, api } from "./api";
export type FocusPayload = { opted_in: true; attentive_pct: number; away_seconds: number; samples: number; paused_seconds: number; sample_fps: 1; tracker_version: string };
export type FocusMine = { attentive_pct: number; away_seconds: number; paused_seconds: number; samples: number; is_valid: boolean };
export type FocusResult = { mine: FocusMine | null; comparison: { n: number; median_pct: number; position: "above" | "around" | "below" } | null };
const choice = (uid: number, sid: number) => `studyflow-focus-choice:${uid}:${sid}`;
export function chooseFocus(uid: number, sid: number, on: boolean) { try { if (on) sessionStorage.setItem(choice(uid,sid), "yes"); else sessionStorage.removeItem(choice(uid,sid)); } catch { /* No saved opt-in means no camera. */ } }
export function wantsFocus(uid: number, sid: number) { try { return sessionStorage.getItem(choice(uid,sid)) === "yes"; } catch { return false; } }
type Pending = { uid: number; pid: number; end: number; payload: FocusPayload };
const pendingKey = (pid: number) => `studyflow-focus-pending:${pid}`;
// This queue contains only numeric summaries and routing IDs. No frames, poses or landmarks.
export function queueFocus(value: Pending) { try { sessionStorage.setItem(pendingKey(value.pid), JSON.stringify(value)); } catch { /* The room also submits directly while open. */ } }
export function adjustFocusEnd(uid: number, pid: number, actualEnd: number) {
  try {
    const raw=sessionStorage.getItem(pendingKey(pid)); if(!raw) return;
    const item:Pending=JSON.parse(raw); if(item.uid!==uid || actualEnd>=item.end) return;
    item.payload.paused_seconds=Math.max(0,item.payload.paused_seconds-Math.floor((item.end-actualEnd)/1000));
    item.end=actualEnd; queueFocus(item);
  } catch { /* Optional storage can be unavailable. */ }
}
export async function flushFocus(uid: number, token: string) {
  const pending: Pending[] = [];
  try { for (let i=0;i<sessionStorage.length;i++) { const key=sessionStorage.key(i)!; if (key.startsWith("studyflow-focus-pending:")) pending.push(JSON.parse(sessionStorage.getItem(key)!)); } } catch { return; }
  for (const item of pending) {
    if (item.uid !== uid || Date.now() < item.end) continue;
    if (Date.now() > item.end + 30*60_000) { sessionStorage.removeItem(pendingKey(item.pid)); continue; }
    try { await api(`/participants/${item.pid}/focus-summary`, { method: "POST", token, body: item.payload }); sessionStorage.removeItem(pendingKey(item.pid)); }
    catch (error) { if (error instanceof APIError && (error.status === 410 || (error.status === 409 && error.message.includes("already saved")))) sessionStorage.removeItem(pendingKey(item.pid)); }
  }
}
