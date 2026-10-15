"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { ErrorMessage, GroupBar, field } from "@/components/group-ui";
import { api } from "@/lib/api";
import type { Group } from "@/lib/groups";

const colours = ["bg-rose-400", "bg-indigo-400", "bg-amber-500", "bg-sky-500", "bg-teal-500", "bg-violet-400"];
export function Avatar({ name, id = 0, muted = false }: { name: string; id?: number; muted?: boolean }) {
  const initials = name.trim().split(/\s+/).slice(0, 2).map(word => word[0]).join("").toUpperCase();
  return <span aria-hidden="true" className={`flex size-11 shrink-0 items-center justify-center rounded-full text-sm font-bold ${muted ? "bg-slate-100 text-slate-500" : `${colours[id % colours.length]} text-white`}`}>{initials}</span>;
}

export function StreakCard({ group }: { group: Group }) {
  return <section aria-label="Squad streak" className="card flex h-full flex-col p-4 md:p-6">
    <h2 className="text-sm font-semibold text-slate-500">Squad streak</h2>
    <p className="mt-3 flex flex-wrap items-baseline gap-2"><span aria-hidden="true" className="self-center text-2xl md:text-3xl">🔥</span><b className="text-4xl text-amber-600 md:text-5xl">{group.streak}</b><span className="font-bold">days</span></p>
    {!!group.streak_history?.length && <div aria-label="Recent streak days" className="mt-4 flex gap-1.5">{group.streak_history.map(day => <span key={day.date} title={`${day.date}: ${day.outcome}`} aria-label={`${day.date}: ${day.outcome}`} className={`h-2.5 flex-1 rounded-full ${day.outcome === "kept" ? "bg-amber-400" : day.outcome === "frozen" ? "bg-sky-300" : "bg-slate-200"}`} />)}</div>}
    <p className="mt-auto pt-4 text-xs font-bold text-sky-700">❄ {group.freezes_remaining} {group.freezes_remaining === 1 ? "freeze" : "freezes"} left this week</p>
    <p className="mt-2 hidden text-xs leading-relaxed text-slate-500 md:block">Checked at 02:00 Lagos.{group.last_evaluated_date ? ` Through ${group.last_evaluated_date}.` : " Your first day is still ahead."}{group.streak_paused ? " At least 3 members are needed at the start of a day." : ""}</p>
  </section>;
}

export function DailyGoal({ group }: { group: Group }) {
  const complete = group.completed_today >= group.member_count;
  return <section aria-label="Today's squad goal" className={`card flex h-full flex-col p-4 md:p-6 ${complete ? "ring-2 ring-amber-300" : ""}`}>
    <h2 className="text-sm font-semibold text-slate-500">Today’s squad goal</h2>
    <p className="mt-3 text-3xl font-extrabold md:text-4xl">{group.completed_today}<span className="text-lg text-slate-400"> / {group.member_count}</span></p>
    <p className="mt-2 text-sm font-bold">{complete ? "Daily squad goal complete!" : `${group.member_count} sessions together`}</p>
    <div role="progressbar" aria-label="Squad sessions completed today" aria-valuemin={0} aria-valuemax={Math.max(group.completed_today, group.member_count)} aria-valuenow={group.completed_today} className="mt-4 h-2.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.min(100, 100 * group.completed_today / Math.max(1, group.member_count))}%` }} /></div>
    <p className="mt-auto pt-4 text-xs leading-relaxed text-slate-500"><span className="hidden md:inline">Completed sessions today, Lagos time. </span>Solo counts too.</p>
  </section>;
}

export function StudiedToday({ group }: { group: Group }) {
  const { user } = useAuth();
  return <section className="card p-5 md:p-6"><div className="flex justify-between gap-3"><h2 className="font-bold md:text-lg">Studied today</h2><p className="text-sm font-semibold text-slate-500">{group.members.filter(m => m.completed_today > 0).length} of {group.member_count}</p></div><ul className="mt-5 grid grid-cols-4 gap-x-2 gap-y-4 sm:grid-cols-6">{group.members.map(member => <li key={member.user_id} className="flex min-w-0 flex-col items-center gap-2 text-center"><div className="relative"><Avatar name={member.display_name} id={member.user_id} muted={!member.completed_today} />{!!member.completed_today && <span aria-label="Studied today" className="absolute -right-1 -bottom-1 flex size-5 items-center justify-center rounded-full bg-brand-500 text-xs font-bold text-white ring-2 ring-white">✓</span>}</div><span className="max-w-full text-xs font-semibold wrap-anywhere">{member.user_id === user?.id ? "You" : member.display_name}</span></li>)}</ul><Link prefetch={false} href={`/groups/${group.id}`} className="mt-4 inline-flex min-h-11 items-center text-sm font-bold text-brand-700">Visit your squad →</Link></section>;
}

export function GroupProgress({ groupId, details = false }: { groupId?: number; details?: boolean }) {
  const { token } = useAuth();
  const [groups, setGroups] = useState<Group[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (!token) return;
    let active = true;
    async function load() {
      try {
        const data = groupId ? [await api<Group>(`/groups/${groupId}`, { token: token! })] : await api<Group[]>("/groups", { token: token! });
        if (active) { setGroups(data); setError(""); }
      } catch (e) { if (active) setError((e as Error).message); }
    }
    void load(); const interval = setInterval(() => { if (!document.hidden) void load(); }, 30000);
    return () => { active = false; clearInterval(interval); };
  }, [token, groupId]);
  const group = groups.find(g => String(g.id) === selected) ?? groups[0];
  if (error) return <ErrorMessage message={error} />;
  if (!group) return null;
  return <div role="region" className="space-y-5" aria-label="Current squad progress">{groups.length > 1 && <label className="block text-sm font-bold">Squad progress<select aria-label="Squad progress" value={group.id} onChange={e => setSelected(e.target.value)} className={`studyflow-select ${field}`}>{groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></label>}<GroupBar name={group.name} points={group.weekly_points} target={group.weekly_target} compact />{details && <><DailyGoal group={group} /><StreakCard group={group} /></>}</div>;
}
