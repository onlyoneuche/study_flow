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
  if (!user) return <section className="card mx-auto max-w-lg space-y-5 p-7"><h1 className="text-2xl font-extrabold">Your squad is waiting</h1><p className="text-slate-500">Sign in to study with your friends.</p><Link prefetch={false} className={primary} href={`/auth/sign-in?next=${encodeURIComponent(next)}`}>Sign in</Link> <Link prefetch={false} className={secondary} href={`/auth/sign-up?next=${encodeURIComponent(next)}`}>Create account</Link></section>;
  return children;
}
export function GroupBar({ name, points, target, compact = false }: { name: string; points: number; target: number; compact?: boolean }) {
  const fill = target ? Math.max(0, Math.min(100, Math.floor(100 * points / target))) : 0;
  return <section aria-label="Weekly squad progress" className={`relative overflow-hidden rounded-[26px] bg-linear-to-br from-brand-600 to-brand-700 text-white ${compact ? "p-5" : "p-5 md:p-8"}`}>
    <span aria-hidden="true" className="pointer-events-none absolute -top-16 -right-8 size-52 rounded-full bg-white/10" />
    <div className="relative"><p className="text-sm font-semibold text-brand-100 md:text-base">{name} · this week</p><div className="mt-3 flex flex-wrap items-baseline justify-between gap-2"><p className={`${compact ? "text-3xl" : "text-[44px] leading-none md:text-[64px]"} font-extrabold`}>{points} <span className={`${compact ? "text-base" : "text-xl md:text-2xl"} font-semibold text-brand-100`}>/ {target} pts</span></p><span className="font-bold">{fill}%</span></div><div role="progressbar" aria-label="Weekly squad points" aria-valuenow={Math.max(0, points)} aria-valuemin={0} aria-valuemax={Math.max(target, points)} className="mt-4 h-3 overflow-hidden rounded-full bg-white/20 md:h-4"><div className="h-full rounded-full bg-linear-to-r from-amber-300 to-amber-400" style={{ width: `${fill}%` }} /></div><p className="mt-3 text-sm text-brand-50">{points >= target ? "Weekly goal reached. Keep growing together!" : `${Math.max(0, target - points)} pts to go. A little progress from everyone.`}</p><p className="mt-2 text-xs text-brand-100">Week resets Monday 00:00, Lagos time.</p></div>
  </section>;
}
