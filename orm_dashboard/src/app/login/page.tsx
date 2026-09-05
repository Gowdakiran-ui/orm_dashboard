"use client";

import React, { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Sora, JetBrains_Mono } from "next/font/google";
import { motion } from "framer-motion";
import { login } from "@/lib/api";
import { MagneticButton } from "@/components/landing/MagneticButton";

/**
 * Fonts + palette match the marketing landing page (Solar Flare accent on a
 * near-black zinc theme) — scoped to this page only via the wrapper's
 * className, same pattern as src/app/page.tsx. Auth logic below is
 * untouched, this is a styling pass only.
 */
const body = Sora({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-login-body",
});
const dataMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-login-mono",
});

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
    <div
      className={`${body.variable} ${dataMono.variable} relative flex min-h-screen w-full flex-col items-center justify-center overflow-hidden bg-zinc-950 px-4 py-12 font-[family-name:var(--font-login-body)] text-zinc-50`}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_55%_55%_at_50%_40%,black_10%,transparent_75%)]"
      >
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#27272a_1px,transparent_1px),linear-gradient(to_bottom,#27272a_1px,transparent_1px)] bg-[size:64px_64px] opacity-40" />
      </div>

      <motion.form
        onSubmit={handleSubmit}
        initial={{ opacity: 0, y: 24, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 140, damping: 18, mass: 0.7 }}
        className="relative w-full max-w-sm space-y-5 rounded-2xl border border-zinc-800 bg-zinc-900/70 p-8 shadow-[0_8px_30px_rgba(0,0,0,0.4)] backdrop-blur-xl"
      >
        <div className="space-y-1 text-center">
          <h1 className="font-[family-name:var(--font-login-mono)] text-lg font-extrabold uppercase tracking-wider text-[#FF5E00]">
            ORM Command
          </h1>
          <p className="text-xs text-zinc-400">Sign in to access the intelligence platform</p>
        </div>

        {justActivated && (
          <p className="rounded border border-emerald-500/20 bg-emerald-500/10 p-2 text-center text-xs text-emerald-400">
            Account activated. Sign in with your new password.
          </p>
        )}

        <div className="space-y-2">
          <label className="block font-[family-name:var(--font-login-mono)] text-[10px] uppercase tracking-wider text-zinc-400">
            Email
          </label>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-100 transition-colors focus:border-[#FF5E00] focus:outline-none"
          />
        </div>

        <div className="space-y-2">
          <label className="block font-[family-name:var(--font-login-mono)] text-[10px] uppercase tracking-wider text-zinc-400">
            Password
          </label>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-100 transition-colors focus:border-[#FF5E00] focus:outline-none"
          />
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}

        <MagneticButton
          as={motion.button}
          type="submit"
          disabled={loading}
          strength={0.15}
          whileTap={{ scale: 0.97 }}
          className="w-full rounded-lg bg-[#FF5E00] px-4 py-3 font-[family-name:var(--font-login-mono)] text-xs font-bold uppercase tracking-wider text-[#1A0900] transition-colors hover:bg-[#FFB703] disabled:opacity-50"
        >
          {loading ? "Signing in..." : "Sign In"}
        </MagneticButton>
      </motion.form>
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
