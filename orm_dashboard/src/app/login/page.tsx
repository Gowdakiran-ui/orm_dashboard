"use client";

import React, { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { login } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const justActivated = searchParams.get("activated") === "1";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email, password);
      router.push("/dashboard");
      router.refresh();
    } catch (err: any) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-[#030712] text-slate-100 font-mono">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-5 rounded-2xl border border-[#1F2937] bg-[#060B18]/80 p-8"
      >
        <div className="space-y-1 text-center">
          <h1 className="text-lg font-extrabold uppercase tracking-wider text-[#D4AF37]">ORM Command</h1>
          <p className="text-xs text-slate-400">Sign in to access the intelligence platform</p>
        </div>

        {justActivated && (
          <p className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded p-2 text-center">
            Account activated. Sign in with your new password.
          </p>
        )}

        <div className="space-y-2">
          <label className="block text-[10px] uppercase tracking-wider text-slate-400">Email</label>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded border border-[#1F2937] bg-[#030712] px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-[#D4AF37]"
          />
        </div>

        <div className="space-y-2">
          <label className="block text-[10px] uppercase tracking-wider text-slate-400">Password</label>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded border border-[#1F2937] bg-[#030712] px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-[#D4AF37]"
          />
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-[#D4AF37] px-4 py-2 text-xs font-bold uppercase tracking-wider text-[#030712] transition-colors hover:bg-[#F3C63F] disabled:opacity-50"
        >
          {loading ? "Signing in..." : "Sign In"}
        </button>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
