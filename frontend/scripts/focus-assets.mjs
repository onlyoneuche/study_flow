import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
const root = path.resolve(import.meta.dirname, '..');
const target = path.join(root, 'public/focus-assets');
await mkdir(target, { recursive: true });
await cp(path.join(root, 'vendor/mediapipe'), path.join(target, 'licence'), { recursive: true });
await cp(path.join(root, 'node_modules/@mediapipe/tasks-vision/wasm'), path.join(target, 'wasm'), { recursive: true });
const model = path.join(target, 'face_landmarker.task');
// Official versioned model; downloaded only at setup/build, never from a user's camera worker.
const url = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';
let bytes;
try { bytes = await readFile(model); } catch {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Focus model download failed: ${response.status}`);
  bytes = Buffer.from(await response.arrayBuffer());
}
if (createHash('sha256').update(bytes).digest('hex') !== '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff') throw new Error('Invalid Focus Tracker model bundle');
await writeFile(model, bytes);
console.log(`Self-hosted focus assets ready; model SHA-256 ${createHash('sha256').update(bytes).digest('hex')}`);
