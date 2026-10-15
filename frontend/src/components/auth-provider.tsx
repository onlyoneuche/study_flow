"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { api, type User } from "@/lib/api";

const TOKEN_KEY = "studyflow-token";
type Auth = { user: User | null; token: string | null; ready: boolean; signIn: (email: string, password: string) => Promise<void>; signOut: () => Promise<void>; refresh: () => Promise<void> };
const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(async () => {
      let saved: string | null = null;
      try { saved = sessionStorage.getItem(TOKEN_KEY); } catch { /* Storage can be disabled. */ }
      if (saved) {
        try {
          const me = await api<User>("/users/me", { token: saved });
          if (active) { setToken(saved); setUser(me); }
        } catch { /* A fresh sign-in can restore an expired or interrupted session. */ }
      }
      if (active) setReady(true);
    });
    return () => { active = false; };
  }, []);

  async function signIn(email: string, password: string) {
    const result = await api<{ access_token: string }>("/auth/jwt/login", { method: "POST", form: new URLSearchParams({ username: email, password }) });
    const me = await api<User>("/users/me", { token: result.access_token });
    try { sessionStorage.setItem(TOKEN_KEY, result.access_token); } catch { /* In-memory sign-in still works. */ }
    setToken(result.access_token); setUser(me);
  }

  async function signOut() {
    try { if (token) await api("/auth/jwt/logout", { method: "POST", token }); } catch { /* Always clear the local session. */ }
    try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* Storage may be disabled. */ }
    setToken(null); setUser(null);
  }

  async function refresh() { if (token) setUser(await api<User>("/users/me", { token })); }

  return <AuthContext.Provider value={{ user, token, ready, signIn, signOut, refresh }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("AuthProvider is required");
  return context;
}
