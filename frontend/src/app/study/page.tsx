import { Suspense } from "react";
import { StartSession } from "@/components/start-session";
export default function Page() { return <Suspense fallback={<p>Opening your study space…</p>}><StartSession /></Suspense>; }
