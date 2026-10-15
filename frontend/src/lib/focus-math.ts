// Only booleans and counters survive a frame. No images, landmarks or poses are retained.
export class FocusCounts {
  samples = 0; attentive = 0; away = 0;
  private kind: "away" | "look" | null = null;
  private run = 0;
  flush() {
    if (this.kind === "away" && this.run > 20) this.away += this.run;
    else if (this.kind === "away" || (this.kind === "look" && this.run <= 5)) this.attentive += this.run;
    this.kind = null; this.run = 0;
  }
  add(face: boolean, head: boolean) {
    this.samples++;
    const kind = !face ? "away" : !head ? "look" : null;
    if (kind !== this.kind) this.flush();
    if (kind) { this.kind = kind; this.run++; } else this.attentive++;
  }
  summary() { this.flush(); return { samples: this.samples, attentive_pct: this.samples ? Math.floor(100 * this.attentive / this.samples + .5) : 0, away_seconds: this.away }; }
}

export function median(values: number[]) { const sorted = [...values].sort((a,b) => a-b); const i = Math.floor(sorted.length/2); return sorted.length % 2 ? sorted[i] : (sorted[i-1]+sorted[i])/2; }

// MediaPipe supplies column-major canonical-face -> camera transforms. Camera looks down -Z;
// metric Y points up. The face-forward axis has negative Y when looking down.
// Scale does not affect angles.
export function headPose(m: ArrayLike<number>) {
  return { yaw: Math.atan2(m[8], m[10]) * 180 / Math.PI,
    pitch: Math.atan2(m[9], Math.hypot(m[8], m[10])) * 180 / Math.PI };
}
export function headOK(yaw: number, pitch: number, neutral: { yaw: number; pitch: number }) {
  const difference = (a: number, b: number) => ((a-b+540)%360)-180;
  return Math.abs(difference(yaw, neutral.yaw)) <= 30 && difference(pitch, neutral.pitch) >= -45 && difference(pitch, neutral.pitch) <= 20;
}
