"use client";

import { useEffect, useState } from "react";

type Health = {
  status: "ok" | "degraded";
  ollama: { status: "ready" | "model_missing" | "unreachable" | "invalid_response" };
};

const modelMessages: Record<Health["ollama"]["status"], string> = {
  ready: "Local quiz model is ready",
  model_missing: "Quiz model needs to be downloaded",
  unreachable: "Local quiz service is offline",
  invalid_response: "Local quiz service needs attention",
};

async function requestHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch("/api/v1/health", {
    cache: "no-store",
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(6000)]) : AbortSignal.timeout(6000),
  });
  if (!response.ok) throw new Error("API unavailable");
  const body = await response.json() as Health;
  if (!body?.ollama || !Object.hasOwn(modelMessages, body.ollama.status)) throw new Error("Invalid health response");
  return body;
}

export function HealthStatus() {
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(false);
    try {
      setHealth(await requestHealth());
    } catch {
      setError(true);
      setHealth(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void requestHealth(controller.signal).then((body) => {
      if (!controller.signal.aborted) setHealth(body);
    }).catch(() => {
      if (!controller.signal.aborted) setError(true);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, []);

  return <section className="card p-5 md:p-6" aria-label="Connection status">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-lg font-bold text-slate-900">Connection status</h2>
      <button type="button" onClick={() => void refresh()} disabled={loading} className="min-h-11 rounded-xl border border-slate-200 px-4 text-sm font-bold text-brand-700 disabled:opacity-50">{loading ? "Checking…" : "Check again"}</button>
    </div>
    <div role="status" aria-live="polite" className="mt-4 space-y-3 text-sm text-slate-600">
      {loading ? <p>Checking your connection…</p> : error ? <p>We couldn’t connect. Please try again in a moment.</p> : health && <>
        <p className="flex items-center gap-2"><span className="size-2.5 rounded-full bg-brand-500" aria-hidden="true" />StudyFlow is online</p>
        <p className="flex items-center gap-2"><span className={`size-2.5 rounded-full ${health.ollama.status === "ready" ? "bg-brand-500" : "bg-amber-500"}`} aria-hidden="true" />{modelMessages[health.ollama.status]}</p>
      </>}
    </div>
  </section>;
}
