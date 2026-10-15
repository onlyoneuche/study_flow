"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { AccountEntry } from "@/components/account-entry";
import { BrandMark } from "@/components/app-shell";
import { ErrorMessage, GroupBar, field, primary, secondary } from "@/components/group-ui";
import { Avatar, DailyGoal, StreakCard, StudiedToday } from "@/components/study-ui";
import { api } from "@/lib/api";
import type { Dashboard as Data } from "@/lib/dashboard";
import { lagosTime } from "@/lib/sessions";

export function Dashboard() {
  const { user, token, ready } = useAuth();
  const [data, setData] = useState<Data | null>(null);
  const [groupId, setGroupId] = useState("");
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!token) return;
    let active = true; let pending = false;
    async function load() {
      if (pending) return; pending = true;
      try { const result = await api<Data>("/users/me/dashboard", { token: token! }); if (active) { setData(result); setError(""); } }
      catch (e) { if (active) setError((e as Error).message); }
      finally { pending = false; }
    }
    const visible = () => { if (!document.hidden) void load(); };
    void load(); const poll = setInterval(visible, 30000); window.addEventListener("focus", visible);
    return () => { active = false; clearInterval(poll); window.removeEventListener("focus", visible); };
  }, [token, refresh]);
  if (!ready) return <p role="status">Opening your study space…</p>;
  if (!user) return <Welcome />;
  const group = data?.groups.find(g => String(g.id) === groupId) ?? data?.groups[0];
  const live = data?.sessions.filter(s => s.mode === "live" && s.group_id === group?.id).sort((a, b) => a.started_at.localeCompare(b.started_at))[0];
  const hour = data ? Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hourCycle: "h23", timeZone: "Africa/Lagos" }).format(new Date(data.server_now))) : 12;
  return <>
    <header className="mb-6 flex items-center justify-between gap-3 md:mb-8"><div className="min-w-0"><p className="text-sm text-slate-500 md:text-base">Good {hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening"},</p><h1 className="mt-1 text-[26px] leading-tight font-extrabold tracking-tight wrap-anywhere md:text-[34px]">{user.display_name}<span className="hidden sm:inline"> 👋</span></h1></div><div className="flex shrink-0 items-center gap-2"><button aria-label="Refresh dashboard" className="flex min-h-12 min-w-12 items-center justify-center rounded-2xl bg-white text-xl text-slate-500 shadow-sm" onClick={() => setRefresh(n => n + 1)}>↻</button><Link prefetch={false} href="/account" aria-label="Your account" className="flex min-h-12 min-w-12 items-center justify-center"><Avatar name={user.display_name} id={user.id} /></Link></div></header>
    <ErrorMessage message={error} />{error && <Link prefetch={false} href="/auth/sign-in?next=/" className={`${secondary} my-4`}>Sign in to reconnect</Link>}
    {!data && !error && <p role="status">Loading your squad’s progress…</p>}
    {data && <>
      {data.groups.length > 1 && <label className="mb-5 block max-w-sm text-sm font-bold">Your squad<select aria-label="Your squad" value={group?.id ?? ""} onChange={e => setGroupId(e.target.value)} className={`studyflow-select ${field}`}>{data.groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></label>}
      {group ? <>
        <GroupBar name={group.name} points={group.weekly_points} target={group.weekly_target} />
        <div className="mt-4 grid grid-cols-2 gap-3 md:mt-6 md:gap-6 min-[64.0625rem]:grid-cols-3">
          <StreakCard group={group} /><DailyGoal group={group} />
          <section className="card col-span-2 flex flex-col gap-4 border-2 border-brand-100 p-5 md:p-6 min-[64.0625rem]:col-span-1"><p className="text-sm font-semibold text-slate-500">{live?.status === "running" ? "Your squad is studying" : "Next live session"}</p><div className="flex items-center gap-3"><span aria-hidden="true" className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-amber-50 text-2xl">⏱</span><p className="text-lg leading-snug font-extrabold wrap-anywhere">{live ? live.status === "running" ? "Come study together" : `${lagosTime(live.started_at)} Lagos` : "Make time together"}</p></div><p className="text-sm font-semibold text-brand-700">{live ? `${live.planned_minutes} minutes · +5 live bonus` : "Everyone brings their own topic."}</p><Link prefetch={false} href={live ? `/sessions/${live.id}` : `/study?group=${group.id}`} className={`${primary} mt-auto`}>{live ? "Join session" : "Plan a live session"}</Link></section>
          <div className="col-span-2"><StudiedToday group={group} /></div>
          <section className="card col-span-2 flex flex-col gap-4 p-5 md:p-6 min-[64.0625rem]:col-span-1"><h2 className="text-lg font-bold">Studying alone?</h2><p className="text-sm leading-relaxed text-slate-500">Solo sessions fill your squad bar too. You’ve completed {data.weekly_completed} {data.weekly_completed === 1 ? "session" : "sessions"} this Lagos week.</p><Link prefetch={false} href="/study" className={`${secondary} mt-auto border-brand-600 text-brand-700`}>Start solo session</Link></section>
        </div>
      </> : <section className="rounded-[26px] bg-linear-to-br from-brand-600 to-brand-700 p-6 text-white md:p-9"><p className="font-semibold text-brand-100">Your study space is ready</p><h2 className="mt-3 text-3xl leading-tight font-extrabold">A little progress, together.</h2><p className="mt-4 max-w-lg text-sm leading-relaxed text-brand-50">Create a squad or join a friend’s invite. You can also start studying on your own topic right away.</p><div className="mt-6 flex flex-wrap gap-3"><Link prefetch={false} href="/squad" className={`${secondary} border-white text-brand-700`}>Create or join a squad</Link><Link prefetch={false} href="/study" className="inline-flex min-h-12 items-center rounded-2xl border border-white/50 px-5 font-bold">Start solo session</Link></div></section>}
      {!!data.recent.length && <section className="card mt-6 p-5 md:p-6"><div className="flex flex-wrap justify-between gap-3"><h2 className="text-lg font-extrabold">Your recent study</h2><Link prefetch={false} href="/account/ledger" className="inline-flex min-h-11 items-center text-sm font-bold text-brand-700">Your points history →</Link></div><ul className="mt-2 divide-y divide-slate-100">{data.recent.map(study => <li key={study.participant_id} className="flex flex-wrap items-center justify-between gap-3 py-4"><div className="min-w-0"><p className="font-bold wrap-anywhere">{study.topic}</p><p className="mt-1 text-xs text-slate-500">{study.subject} · {study.planned_minutes} min · {study.session_date} · {study.status === "completed" ? "Complete" : study.status === "incomplete" ? "Not enough study time" : study.ended_at ? "Study time saved" : "In progress"}</p></div><Link prefetch={false} href={study.submitted || study.status === "completed" || study.quiz_available ? `/participants/${study.participant_id}/quiz` : `/sessions/${study.session_id}`} className={`${secondary} shrink-0 text-sm`}>{study.submitted || study.status === "completed" ? "View result" : study.quiz_available ? "Open quiz" : study.ended_at ? "View session" : "Resume session"}</Link></li>)}</ul></section>}
    </>}
  </>;
}

function Welcome() {
  return <><header className="mb-6 flex items-center gap-3"><BrandMark /><h1 className="text-2xl font-extrabold tracking-tight md:text-3xl">Welcome to StudyFlow</h1></header><section className="relative overflow-hidden rounded-[26px] bg-linear-to-br from-brand-600 to-brand-700 p-7 text-white md:p-10"><span aria-hidden="true" className="absolute -top-12 -right-12 size-60 rounded-full bg-white/10" /><p className="relative text-sm font-bold text-brand-100">A little progress, every day</p><h2 className="relative mt-4 text-4xl leading-tight font-extrabold tracking-tight md:text-5xl">Your topic. Your pace.<br />Your study squad.</h2><p className="relative mt-5 max-w-xl text-sm leading-relaxed text-brand-50 md:text-base">Make time for what you’re learning, reflect with a quiz, and build a study habit with friends.</p></section><AccountEntry /><div className="mt-6 grid gap-5 md:grid-cols-3">{[["⏱", "Make time", "Pick your topic and study for 25, 45 or 60 minutes, solo or live."], ["🌱", "See your progress", "Take a quiz on your topic. Improvement compares you with your own past."], ["🔥", "Grow together", "Keep a squad streak and fill your weekly bar with friends."]].map(([icon, title, text]) => <section key={title} className="card p-6"><span aria-hidden="true" className="text-3xl">{icon}</span><h2 className="mt-4 text-lg font-bold">{title}</h2><p className="mt-2 text-sm leading-relaxed text-slate-500">{text}</p></section>)}</div></>;
}
