/// <reference lib="webworker" />
import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";
import { FocusCounts, headOK, headPose, median } from "../lib/focus-math";

const worker = self as unknown as DedicatedWorkerGlobalScope;
let model: FaceLandmarker | undefined;
let counts = new FocusCounts();
let calibration: { yaw: number; pitch: number }[] = [];
let calibrationFrames = 0;
let calibrationFaces = 0;
let neutral: { yaw: number; pitch: number } | undefined;
let stopped = false;
function reply(type: string, extra = {}) { worker.postMessage({ type, ...extra }); }
worker.onmessage = async ({ data }) => {
  if (data.type === "init") {
    try {
      const files = await FilesetResolver.forVisionTasks(`${data.origin}/focus-assets/wasm`);
      model = await FaceLandmarker.createFromOptions(files, {
        baseOptions: { modelAssetPath: `${data.origin}/focus-assets/face_landmarker.task`, delegate: "CPU" },
        runningMode: "VIDEO", numFaces: 1, outputFaceBlendshapes: false,
        outputFacialTransformationMatrixes: true, minFacePresenceConfidence: .5,
      });
      counts = new FocusCounts(); calibration = []; calibrationFrames = 0; calibrationFaces = 0; neutral = undefined;
      reply("ready");
    } catch { stopped = true; reply("disabled", { message: "Focus Tracker isn't available on this device" }); }
  }
  if (data.type === "frame") {
    const frame = data.frame as ImageBitmap;
    if (stopped || !model) { frame.close(); return; }
    try {
      const start = performance.now();
      const result = model.detectForVideo(frame, data.timestamp);
      const elapsed = performance.now() - start;
      if (elapsed > 500) { stopped = true; model.close(); reply("disabled", { message: "Focus Tracker isn't available on this device", ...counts.summary() }); return; }
      const matrix = result.facialTransformationMatrixes[0]?.data;
      const face = result.faceLandmarks.length > 0 && !!matrix;
      const pose = face ? headPose(matrix) : null;
      if (!neutral) {
        calibrationFrames++;
        if (pose) { calibrationFaces++; if (calibrationFrames <= 5) calibration.push(pose); }
        if (calibrationFrames === 10) {
          if (calibrationFaces < 8) { stopped = true; model.close(); reply("disabled", { message: "We can't see your face clearly. Try more light in front of you, or turn Focus Tracker off." }); return; }
          neutral = { yaw: median(calibration.map(p => p.yaw)), pitch: median(calibration.map(p => p.pitch)) };
          calibration = []; reply("calibrated");
        } else reply("calibrating", { remaining: 10 - calibrationFrames });
      } else {
        counts.add(face, !!pose && headOK(pose.yaw, pose.pitch, neutral));
        reply("sample", { samples: counts.samples });
      }
    } catch { stopped = true; reply("disabled", { message: "Focus Tracker isn't available on this device", ...counts.summary() }); }
    finally { frame.close(); }
  }
  if (data.type === "pause") counts.flush();
  if (data.type === "stop") { stopped = true; model?.close(); reply("summary", counts.summary()); }
};
