"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth-provider";
import { ErrorMessage, primary, secondary } from "@/components/group-ui";
import { api } from "@/lib/api";

export function JoinPage({ code }: { code: string }) {
  const { token, ready } = useAuth(); const router = useRouter();
  const [preview, setPreview] = useState<{ name: string; member_count: number } | null>(null); const [error, setError] = useState(""); const [retry, setRetry] = useState(0);
  useEffect(() => { if (!ready) return; let active = true;
    const operation = token ? api<{ group_id: number; already_member: boolean }>(`/invites/${encodeURIComponent(code)}/accept`, { method: "POST", token }).then(data => { if (active) router.replace(`/groups/${data.group_id}`); }) : api<{ name: string; member_count: number }>(`/invites/${encodeURIComponent(code)}`).then(data => { if (active) setPreview(data); });
    operation.catch(e => { if (active) setError(e.message); }); return () => { active = false; };
  }, [code, ready, token, router, retry]);
  const next = encodeURIComponent(`/join/${code}`);
  return <section className="card mx-auto mt-6 max-w-lg space-y-6 p-6 text-center md:mt-12 md:p-9"><span className="mx-auto flex size-16 items-center justify-center rounded-2xl bg-brand-100 text-3xl" aria-hidden>📚</span><h1 className="text-3xl font-extrabold">{error ? "Let’s check that invite" : preview ? `Join ${preview.name}` : "Opening your invite…"}</h1><ErrorMessage message={error} />{error ? <><button onClick={() => { setError(""); setRetry(n => n + 1); }} className={secondary}>Try again</button><p className="text-sm text-slate-500">Your friend can ask the owner for a fresh link or an available place.</p><Link href="/squad" className="inline-flex min-h-12 items-center font-bold text-brand-700">Your squads →</Link></> : preview && !token ? <><p className="text-slate-500">{preview.member_count} {preview.member_count === 1 ? "friend is" : "friends are"} building a study habit here. Your topic, together.</p><div className="grid gap-3"><Link href={`/auth/sign-up?next=${next}`} className={primary}>Create account to join</Link><Link href={`/auth/sign-in?next=${next}`} className={secondary}>Sign in to join</Link></div><p className="text-xs text-slate-500">After signing in, you’ll join automatically if a place is available.</p></> : <p role="status" className="text-slate-500">{token ? "Joining your squad…" : "Checking the invite link…"}</p>}</section>;
}
