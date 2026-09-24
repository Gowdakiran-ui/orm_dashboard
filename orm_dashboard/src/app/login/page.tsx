"use client";

import React, { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { login } from "@/lib/api";
import { MagneticButton } from "@/components/landing/MagneticButton";

/**
 * Palette + font match the marketing landing page (src/app/page.tsx) after
 * its round-3 white-balance pass: the landing page now alternates true
 * ivory sections against navy ones instead of one navy field throughout,
 * so this page follows the same two-tone pattern rather than staying
 * all-navy -- ivory page background (matching the landing Hero) with the
 * sign-in card as the navy contrast panel, same relationship as the
 * landing page's "Monitoring tools / XOOP" two-up block. Gold accent
 * (#CEA555, dark navy #0B2D54 text on gold buttons) and Rockwell
 * throughout, unchanged. Scoped to this page only via the wrapper's inline
 * style, same pattern as the landing page -- layout.tsx and the
 * authenticated app keep their own fonts and colors untouched. Auth logic
 * below is unchanged, this is a styling pass only. Rockwell isn't a
 * Google Font, so no next/font loader -- set as a literal CSS font stack
 * instead (real Rockwell where the OS has it installed, a slab-serif
 * fallback chain otherwise), same as the landing page.
 */
const ROCKWELL_STACK = "'Rockwell', 'Rockwell Nova', 'Roboto Slab', Georgia, serif";

const IVORY_BG = "#FBFAF5";
const IVORY_GRID_TEXTURE =
  "linear-gradient(rgba(11,45,84,0.05) 1px,transparent 1px),linear-gradient(90deg,rgba(11,45,84,0.05) 1px,transparent 1px)";

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
      className="relative flex min-h-screen w-full flex-col items-center justify-center overflow-hidden bg-[size:48px_48px] px-4 py-12 font-[family-name:var(--font-login-body)]"
      style={{
        backgroundColor: IVORY_BG,
        backgroundImage: IVORY_GRID_TEXTURE,
        ["--font-login-body" as string]: ROCKWELL_STACK,
        ["--font-login-mono" as string]: ROCKWELL_STACK,
      }}
    >
      <motion.form
        onSubmit={handleSubmit}
        initial={{ opacity: 0, y: 24, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 140, damping: 18, mass: 0.7 }}
        className="relative w-full max-w-sm space-y-5 rounded-2xl border border-[#163F6E] bg-[#0B2D54] p-8 text-white shadow-[0_8px_30px_rgba(11,45,84,0.18)] backdrop-blur-xl"
      >
        <div className="space-y-1 text-center">
          <h1 className="flex items-center justify-center gap-2 font-[family-name:var(--font-login-mono)] text-lg font-extrabold uppercase tracking-wider text-white">
            <Link href="/" className="flex items-center gap-2 transition-opacity hover:opacity-80">
              <span className="h-[9px] w-[9px] rounded-full bg-[#CEA555] shadow-[0_0_0_4px_rgba(206,165,85,0.16)]" />
              XOOP
            </Link>
          </h1>
          <p className="text-xs text-[#93A6C7]">Sign in to access the intelligence platform</p>
        </div>

        {justActivated && (
          <p className="rounded border border-emerald-500/20 bg-emerald-500/10 p-2 text-center text-xs text-emerald-400">
            Account activated. Sign in with your new password.
          </p>
        )}

        <div className="space-y-2">
          <label className="block font-[family-name:var(--font-login-mono)] text-[10px] uppercase tracking-wider text-[#93A6C7]">
            Email
          </label>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-[#163F6E] bg-[#04213F] px-3 py-2.5 text-sm text-white transition-colors focus:border-[#CEA555] focus:outline-none"
          />
        </div>

        <div className="space-y-2">
          <label className="block font-[family-name:var(--font-login-mono)] text-[10px] uppercase tracking-wider text-[#93A6C7]">
            Password
          </label>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-[#163F6E] bg-[#04213F] px-3 py-2.5 text-sm text-white transition-colors focus:border-[#CEA555] focus:outline-none"
          />
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}

        <MagneticButton
          as={motion.button}
          type="submit"
          disabled={loading}
          strength={0.15}
          whileTap={{ scale: 0.97 }}
          className="w-full rounded-lg bg-[#CEA555] px-4 py-3 font-[family-name:var(--font-login-mono)] text-xs font-bold uppercase tracking-wider text-[#0B2D54] transition-colors hover:bg-[#DFC172] disabled:opacity-50"
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
