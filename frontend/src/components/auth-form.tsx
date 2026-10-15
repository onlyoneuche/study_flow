"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, useSyncExternalStore, type FormEvent } from "react";
import { api, bandFor, levels, levelLabel, type EducationLevel } from "@/lib/api";
import { useAuth } from "@/components/auth-provider";

export type AuthAction = "sign-up" | "sign-in" | "forgot-password" | "reset-password" | "verify";
const headings: Record<AuthAction, string> = { "sign-up": "Find your study flow", "sign-in": "Welcome back", "forgot-password": "Let’s get you back in", "reset-password": "A fresh start", verify: "Verify your email" };
const descriptions: Record<AuthAction, string> = { "sign-up": "A little progress, every day. Start with your own account.", "sign-in": "Your study space is waiting for you.", "forgot-password": "Enter your email to request a password reset link.", "reset-password": "Choose a new password for your StudyFlow account.", verify: "Confirm your email to finish setting up your account." };
const inputClass = "mt-2 min-h-12 w-full rounded-2xl border border-slate-200 bg-white px-4 text-base text-slate-900 focus:border-brand-600";
const subscribeHash = (callback: () => void) => { window.addEventListener("hashchange", callback); return () => window.removeEventListener("hashchange", callback); };
const getHash = () => window.location.hash;
const serverHash = () => "";

export function Consent({ secondary, checked, onChange }: { secondary: boolean; checked: boolean; onChange: (checked: boolean) => void }) {
  return <label className="flex cursor-pointer items-start gap-3 rounded-2xl bg-brand-50 p-4 text-sm leading-relaxed text-slate-700">
    <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} required className="mt-0.5 size-5 shrink-0 accent-brand-600" />
    <span>{secondary ? "My parent or guardian has consented to my use of StudyFlow, including the optional on-device camera feature. Video stays on my device and Focus Tracker never changes points." : "I confirm I am 18 or older and can join the university / adult audience band."}</span>
  </label>;
}

export function AuthForm({ action }: { action: AuthAction }) {
  const { signIn, ready, refresh } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const hash = useSyncExternalStore(subscribeHash, getHash, serverHash);
  const token = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  const [level, setLevel] = useState<EducationLevel>("SS2");
  const [consented, setConsented] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const returnQuery = search.get("next") ? `?next=${encodeURIComponent(search.get("next")!)}` : "";
  const secondary = bandFor(level) === "secondary";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setMessage(""); setBusy(true);
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "");
    const password = String(data.get("password") ?? "");
    try {
      if (action === "sign-up") {
        await api("/auth/register", { method: "POST", body: { email, password, display_name: data.get("display_name"), level, audience_band: bandFor(level), guardian_consent: secondary && consented, adult_confirmation: !secondary && consented } });
        setMessage("Account created. Your verification email is printed in the local server console. You can sign in now.");
      } else if (action === "sign-in") {
        await signIn(email, password);
        const next = search.get("next");
        // Preserve local invite destinations; never navigate to another origin.
        let destination = "/account";
        try {
          const url = new URL(next ?? "/account", window.location.origin);
          if (url.origin === window.location.origin) destination = url.pathname + url.search + url.hash;
        } catch { /* Invalid return addresses fall back to the account page. */ }
        router.replace(destination);
      } else if (action === "forgot-password") {
        await api("/auth/forgot-password", { method: "POST", body: { email } });
        setMessage("If an active account uses this email, a reset link has been printed in the local server console.");
      } else {
        if (!token) throw new Error("Open the full link from the local server console, or request a new link.");
        await api(action === "verify" ? "/auth/verify" : "/auth/reset-password", { method: "POST", body: action === "verify" ? { token } : { token, password } });
        if (action === "verify") await refresh();
        window.history.replaceState(null, "", window.location.pathname);
        setMessage(action === "verify" ? "Email verified. You’re ready to sign in." : "Password updated. Sign in with your new password.");
      }
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Please try again."); }
    finally { setBusy(false); }
  }

  return <div className="mx-auto w-full max-w-lg">
    <div className="mb-7"><p className="text-sm font-bold text-brand-700">Your topic. Your pace. Your squad.</p><h1 className="mt-3 text-3xl font-extrabold tracking-tight text-slate-900 md:text-4xl">{headings[action]}</h1><p className="mt-3 text-sm leading-relaxed text-slate-500">{descriptions[action]}</p></div>
    <div className="card p-5 md:p-7">
      <form onSubmit={submit} className="space-y-5">
        {action === "sign-up" && <label className="block text-sm font-bold">Display name<input name="display_name" autoComplete="nickname" maxLength={100} required className={inputClass} /></label>}
        {["sign-up", "sign-in", "forgot-password"].includes(action) && <label className="block text-sm font-bold">Email<input name="email" type="email" autoComplete="email" required className={inputClass} /></label>}
        {["sign-up", "sign-in", "reset-password"].includes(action) && <label className="block text-sm font-bold">{action === "reset-password" ? "New password" : "Password"}<input aria-label={action === "reset-password" ? "New password" : "Password"} aria-describedby={action === "sign-in" ? undefined : "password-hint"} name="password" type="password" autoComplete={action === "sign-in" ? "current-password" : "new-password"} required minLength={action === "sign-in" ? undefined : 8} maxLength={128} className={inputClass} />{action !== "sign-in" && <span id="password-hint" className="mt-2 block text-xs font-normal text-slate-500">Use 8–128 characters.</span>}</label>}
        {action === "sign-up" && <>
          <label className="block text-sm font-bold">Education level<select value={level} onChange={(event) => { setLevel(event.target.value as EducationLevel); setConsented(false); }} className={`studyflow-select ${inputClass}`}>{levels.map((value) => <option key={value} value={value}>{levelLabel(value)}</option>)}</select></label>
          <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Audience band: <strong>{secondary ? "Secondary" : "University / adult"}</strong>. Squads stay within your band.</p>
          <Consent secondary={secondary} checked={consented} onChange={setConsented} />
        </>}
        {error && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
        {message && <p role="status" className="rounded-xl bg-brand-50 p-3 text-sm leading-relaxed text-brand-800">{message}</p>}
        {!message && <button disabled={busy || !ready} className="min-h-13 w-full rounded-2xl bg-brand-600 px-5 font-bold text-white hover:bg-brand-700 disabled:opacity-50">{busy ? "One moment…" : action === "sign-up" ? "Create account" : action === "sign-in" ? "Sign in" : action === "forgot-password" ? "Send reset link" : action === "verify" ? "Verify email" : "Set new password"}</button>}
      </form>
      <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-sm font-semibold text-brand-700">
        {action !== "sign-in" && <Link className="inline-flex min-h-11 items-center" href={`/auth/sign-in${returnQuery}`}>Sign in</Link>}
        {action === "sign-in" && <><Link className="inline-flex min-h-11 items-center" href={`/auth/sign-up${returnQuery}`}>Create account</Link><Link className="inline-flex min-h-11 items-center" href={`/auth/forgot-password${returnQuery}`}>Forgot password?</Link></>}
        {action === "reset-password" && <Link className="inline-flex min-h-11 items-center" href={`/auth/forgot-password${returnQuery}`}>Request a new link</Link>}
      </div>
    </div>
  </div>;
}
