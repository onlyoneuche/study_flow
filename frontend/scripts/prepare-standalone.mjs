import { cp } from "node:fs/promises";

// Next.js standalone output needs its public assets alongside the generated server.
await cp("public", ".next/standalone/public", { recursive: true });
await cp(".next/static", ".next/standalone/.next/static", { recursive: true });
