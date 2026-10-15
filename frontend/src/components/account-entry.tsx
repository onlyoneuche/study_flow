"use client";

import Link from "next/link";
import { useAuth } from "@/components/auth-provider";

export function AccountEntry() {
  const { user, ready } = useAuth();
  if (!ready) return <p className="mt-5 text-sm text-slate-500" role="status">Loading your account…</p>;
  return <div className="mt-5 flex flex-wrap items-center gap-3">
    {user ? <Link prefetch={false} href="/account" className="inline-flex min-h-12 items-center rounded-2xl bg-brand-600 px-5 font-bold text-white">Your account · {user.display_name}</Link> : <>
      <Link prefetch={false} href="/auth/sign-up" className="inline-flex min-h-12 items-center rounded-2xl bg-brand-600 px-5 font-bold text-white">Create account</Link>
      <Link prefetch={false} href="/auth/sign-in" className="inline-flex min-h-12 items-center rounded-2xl border border-brand-600 px-5 font-bold text-brand-700">Sign in</Link>
    </>}
  </div>;
}
