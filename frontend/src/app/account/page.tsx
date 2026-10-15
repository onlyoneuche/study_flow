"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth-provider";
import { HealthStatus } from "@/components/health-status";
import { Consent } from "@/components/auth-form";
import { api, bandFor, levels, levelLabel, type EducationLevel, type User } from "@/lib/api";

export default function Account() {
  const { user, ready, signOut, refresh, token } = useAuth();
  const router = useRouter();
  if (!ready) return <p role="status">Loading your account…</p>;
  if (!user) return <section className="card mx-auto max-w-lg p-6"><h1 className="text-2xl font-extrabold">Your study space awaits</h1><Link prefetch={false} href="/auth/sign-in?next=/account" className="mt-5 inline-flex min-h-12 items-center rounded-2xl bg-brand-600 px-5 font-bold text-white">Sign in</Link></section>;
  return <Profile key={user.id} user={user} token={token!} refresh={refresh} signOut={async () => { await signOut(); router.replace("/auth/sign-in"); }} />;
}

function Profile({ user, token, refresh, signOut }: { user: User; token: string; refresh: () => Promise<void>; signOut: () => Promise<void> }) {
  const [level, setLevel] = useState(user.level);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const secondary = bandFor(level) === "secondary";
  const needsConsent = secondary ? !user.guardian_consent_at : !user.adult_confirmed_at;
  const inputClass = "mt-2 min-h-12 w-full rounded-2xl border border-slate-200 bg-white px-4 text-base font-normal";

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      await api("/users/me", { method: "PATCH", token, body: { display_name: new FormData(event.currentTarget).get("display_name"), level, guardian_consent: secondary && consent, adult_confirmation: !secondary && consent } });
      await refresh(); setMessage("Profile saved.");
    } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  async function verify() {
    setError(""); setMessage(""); setBusy(true);
    try { await api("/auth/request-verify-token", { method: "POST", body: { email: user.email } }); setMessage("A verification link has been printed in the local server console."); }
    catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }

  return <div className="mx-auto max-w-2xl">
    <h1 className="mb-6 text-3xl font-extrabold tracking-tight">Your account</h1>
    <section className="card p-5 md:p-7">
      <div className="mb-6"><p className="font-semibold break-all">{user.email}</p><p className={`mt-2 text-sm font-semibold ${user.is_verified ? "text-brand-700" : "text-amber-700"}`}>{user.is_verified ? "Email verified" : "Email not verified yet"}</p>{!user.is_verified && <button disabled={busy} onClick={() => void verify()} className="mt-2 min-h-11 font-bold text-brand-700">Resend verification email</button>}</div>
      <form onSubmit={save} className="space-y-5">
        <label className="block text-sm font-bold">Display name<input name="display_name" defaultValue={user.display_name} maxLength={100} required className={inputClass} /></label>
        <label className="block text-sm font-bold">Education level<select value={level} onChange={(event) => { setLevel(event.target.value as EducationLevel); setConsent(false); }} className={`studyflow-select ${inputClass}`}>{levels.map((value) => <option key={value} value={value}>{levelLabel(value)}</option>)}</select></label>
        <p className="text-sm text-slate-500">Audience band: {secondary ? "Secondary" : "University / adult"}. A new level starts its own quiz baseline.</p>
        {needsConsent && <Consent secondary={secondary} checked={consent} onChange={setConsent} />}
        {error && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
        {message && <p role="status" className="rounded-xl bg-brand-50 p-3 text-sm text-brand-800">{message}</p>}
        <button disabled={busy} className="min-h-12 rounded-2xl bg-brand-600 px-5 font-bold text-white disabled:opacity-50">{busy ? "One moment…" : "Save profile"}</button>
      </form>
      <div className="mt-6 flex flex-wrap gap-4 border-t border-slate-100 pt-4 text-sm font-bold text-brand-700"><Link prefetch={false} href="/auth/forgot-password" className="inline-flex min-h-11 items-center">Reset password</Link><button onClick={() => void signOut()} className="min-h-11">Sign out</button></div>
    </section>
    <div className="mt-6"><HealthStatus /></div>
  </div>;
}
