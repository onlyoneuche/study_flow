import { Suspense } from "react";
import { notFound } from "next/navigation";
import { AuthForm, type AuthAction } from "@/components/auth-form";

const actions: AuthAction[] = ["sign-up", "sign-in", "forgot-password", "reset-password", "verify"];
export default async function AuthPage({ params }: { params: Promise<{ action: string }> }) {
  const { action } = await params;
  if (!actions.includes(action as AuthAction)) notFound();
  return <Suspense fallback={<p role="status">Getting your study space ready…</p>}><AuthForm key={action} action={action as AuthAction} /></Suspense>;
}
