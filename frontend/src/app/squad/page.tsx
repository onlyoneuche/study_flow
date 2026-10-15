"use client";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth-provider";
import { AuthGate, ErrorMessage, field, primary, secondary } from "@/components/group-ui";
import { api } from "@/lib/api";
import type { Group } from "@/lib/groups";

export default function SquadPage() {
  const { token } = useAuth();
  const router = useRouter();
  const [groups, setGroups] = useState<Group[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!token) return; let active = true; api<Group[]>("/groups", { token }).then(data => { if (active) setGroups(data); }).catch(e => { if (active) setError(e.message); }); return () => { active = false; }; }, [token]);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!token) return; setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try { const group = await api<Group>("/groups", { method: "POST", token, body: { name: data.get("name"), max_members: Number(data.get("max_members")) } }); router.push(`/groups/${group.id}`); }
    catch (e) { setError(e instanceof Error ? e.message : "Please try again."); } finally { setBusy(false); }
  }
  function join(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const code = String(new FormData(event.currentTarget).get("code")).trim().toUpperCase(); router.push(`/join/${encodeURIComponent(code)}`); }
  return <AuthGate next="/squad"><div className="mb-7"><p className="text-sm font-bold text-brand-700">Better together</p><h1 className="mt-2 text-3xl font-extrabold">Your squads</h1><p className="mt-2 text-slate-500">Up to three groups. Your own topic, a shared habit.</p></div><ErrorMessage message={error} /><div className="mt-6 grid items-start gap-6 md:grid-cols-2"><section className="space-y-4"><h2 className="text-lg font-bold">My groups · {groups.length} / 3</h2>{groups.map(group => <Link key={group.id} href={`/groups/${group.id}`} className="card flex min-h-28 items-center justify-between gap-3 p-6"><div><p className="text-lg font-extrabold">{group.name}</p><p className="mt-2 text-sm text-slate-500">{group.member_count} / {group.max_members} members · {group.audience_band === "secondary" ? "Secondary" : "University / adult"}</p></div><span className="text-2xl text-brand-700" aria-hidden>→</span></Link>)}{!groups.length && <p className="card p-6 text-slate-500">Start a squad or use a friend’s invite link.</p>}<form onSubmit={join} className="card space-y-4 p-6"><label className="block text-sm font-bold">Have an invite code?<input name="code" placeholder="K7Q29PXA" required maxLength={8} className={field} autoCapitalize="characters" /></label><button className={secondary}>Join by code</button></form></section><form onSubmit={create} className="card space-y-5 p-6 md:p-8"><h2 className="text-xl font-extrabold">Create a group</h2><label className="block text-sm font-bold">Group name<input name="name" required maxLength={100} className={field} placeholder="Study Squad" /></label><label className="block text-sm font-bold">Member capacity<select name="max_members" defaultValue="8" className={`studyflow-select ${field}`}>{[3,4,5,6,7,8].map(n => <option key={n} value={n}>{n} members</option>)}</select></label><p className="rounded-2xl bg-amber-50 p-4 text-sm leading-relaxed text-amber-900">Your level sets the group’s audience band. Invite at least two friends to activate the group streak.</p><button disabled={busy || groups.length >= 3} className={`${primary} w-full`}>{busy ? "Creating…" : "Create group"}</button></form></div></AuthGate>;
}
