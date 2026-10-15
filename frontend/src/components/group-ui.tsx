"use client";
import Link from "next/link";
import { useAuth } from "@/components/auth-provider";

export const field = "mt-2 min-h-12 w-full rounded-2xl border border-slate-200 bg-white px-4 text-base";
export const primary = "inline-flex min-h-12 items-center justify-center rounded-2xl bg-brand-600 px-5 font-bold text-white hover:bg-brand-700 disabled:opacity-50";
export const secondary = "inline-flex min-h-12 items-center justify-center rounded-2xl border border-slate-200 bg-white px-5 font-bold text-slate-700 disabled:opacity-50";
export function ErrorMessage({ message }: { message: string }) { return message && <p role="alert" className="rounded-2xl bg-rose-50 p-4 text-sm leading-relaxed text-rose-800">{message}</p>; }
export function AuthGate({ next, children }: { next: string; children: React.ReactNode }) {
  const { user, ready } = useAuth();
  if (!ready) return <p role="status">Opening your study space…</p>;
  if (!user) return <section className="card mx-auto max-w-lg space-y-5 p-7"><h1 className="text-2xl font-extrabold">Your squad is waiting</h1><p className="text-slate-500">Sign in to study with your friends.</p><Link className={primary} href={`/auth/sign-in?next=${encodeURIComponent(next)}`}>Sign in</Link> <Link className={secondary} href={`/auth/sign-up?next=${encodeURIComponent(next)}`}>Create account</Link></section>;
  return children;
}
export function GroupBar({ name, points, target }: { name: string; points: number; target: number }) {
  return <div className="rounded-[22px] bg-brand-600 p-6 text-white md:p-8"><p className="text-sm font-semibold text-brand-100">{name} this week</p><div className="mt-3 flex flex-wrap items-baseline justify-between gap-2"><h2 className="text-3xl font-extrabold">{points} <span className="text-lg font-semibold text-brand-100">/ {target} pts</span></h2><span className="font-bold">{target ? Math.min(100, Math.floor(100 * points / target)) : 0}%</span></div><div role="progressbar" aria-label="Weekly group points" aria-valuenow={points} aria-valuemin={0} aria-valuemax={Math.max(target, points)} className="mt-4 h-3 overflow-hidden rounded-full bg-brand-800/50"><div className="h-full rounded-full bg-amber-300" style={{ width: `${Math.min(100, 100 * points / Math.max(1, target))}%` }} /></div><p className="mt-3 text-sm text-brand-50">A little progress from everyone. Week resets Monday, Lagos time.</p></div>;
}
