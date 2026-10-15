"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { AuthGate, ErrorMessage } from "@/components/group-ui";
import { api } from "@/lib/api";
import { awardNames } from "@/lib/quizzes";

type Entry = { id: number; group_name: string; component: string; points: number; lagos_date: string; participant_id: number };
export default function LedgerPage() {
  const { token } = useAuth(); const [entries, setEntries] = useState<Entry[]>([]); const [error, setError] = useState("");
  useEffect(() => { if (!token) return; let active = true; api<{ entries: Entry[] }>("/users/me/ledger", { token }).then(data => { if (active) setEntries(data.entries); }).catch(e => { if (active) setError(e.message); }); return () => { active = false; }; }, [token]);
  return <AuthGate next="/account/ledger"><Link prefetch={false} href="/ranks" className="inline-flex min-h-12 items-center font-bold text-brand-700">← Rankings</Link><h1 className="mt-4 text-3xl font-extrabold">Your points history</h1><p className="mt-3 text-sm text-slate-500">This Lagos week · each credit stays in your group’s history.</p><ErrorMessage message={error} /><ul className="card mt-6 divide-y divide-slate-100 p-5 md:p-7">{entries.map(entry => <li key={entry.id} className="flex items-center justify-between gap-3 py-4"><div className="min-w-0"><p className="break-words font-bold">{awardNames[entry.component] ?? entry.component}</p><p className="mt-1 break-words text-xs text-slate-500">{entry.group_name} · {entry.lagos_date}</p></div><span className="text-xl font-extrabold text-brand-700">{entry.points >= 0 ? "+" : ""}{entry.points}</span></li>)}{!entries.length && <li className="py-4 text-sm text-slate-500">Your next completed session can start this week’s points history.</li>}</ul></AuthGate>;
}
