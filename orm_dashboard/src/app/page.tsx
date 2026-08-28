"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Mail,
  Radar,
  Activity,
  ShieldAlert,
  TrendingUp,
  LayoutDashboard,
  Sparkles,
} from "lucide-react";

const CONTACT_EMAIL = "contact@onlynereputation.com";

/**
 * Scroll-triggered reveal wrapper. Mirrors the fadeInUp treatment already
 * used across the dashboard (globals.css) instead of introducing a new
 * animation system.
 */
function Reveal({
  children,
  className = "",
  delayMs = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delayMs?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15 }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      style={{ transitionDelay: visible ? `${delayMs}ms` : "0ms" }}
      className={`transition-all duration-700 ease-out ${
        visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
      } ${className}`}
    >
      {children}
    </div>
  );
}

function HeroVisual() {
  return (
    <div className="relative mx-auto aspect-square w-full max-w-md">
      <div className="absolute inset-0 rounded-full bg-[radial-gradient(circle_at_center,rgba(212,175,55,0.18),transparent_65%)] blur-2xl" />
      <svg viewBox="0 0 400 400" className="relative h-full w-full">
        <defs>
          <radialGradient id="scoreGrad" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#D4AF37" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#D4AF37" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#D4AF37" />
            <stop offset="100%" stopColor="#60A5FA" />
          </linearGradient>
        </defs>

        {/* orbiting rings */}
        <circle cx="200" cy="200" r="160" fill="none" stroke="#1F2937" strokeWidth="1" />
        <circle
          cx="200"
          cy="200"
          r="160"
          fill="none"
          stroke="url(#ringGrad)"
          strokeWidth="1.5"
          strokeDasharray="8 10"
          className="animate-radarRing"
        />
        <circle cx="200" cy="200" r="115" fill="none" stroke="#1F2937" strokeWidth="1" />
        <circle cx="200" cy="200" r="70" fill="url(#scoreGrad)" />

        {/* mention nodes connected to the center score */}
        {[
          { x: 90, y: 110, delay: "0s" },
          { x: 320, y: 95, delay: "0.4s" },
          { x: 340, y: 250, delay: "0.8s" },
          { x: 220, y: 340, delay: "1.2s" },
          { x: 70, y: 290, delay: "0.2s" },
        ].map((n, i) => (
          <g key={i}>
            <line
              x1="200"
              y1="200"
              x2={n.x}
              y2={n.y}
              stroke="#D4AF37"
              strokeOpacity="0.25"
              strokeWidth="1"
              strokeDasharray="4 4"
              className="animate-pipelineFlow"
            />
            <circle
              cx={n.x}
              cy={n.y}
              r="6"
              fill="#0B1120"
              stroke="#D4AF37"
              strokeWidth="1.5"
              className="animate-enginePulse"
              style={{ animationDelay: n.delay }}
            />
          </g>
        ))}

        {/* center score dial */}
        <circle cx="200" cy="200" r="46" fill="#060B18" stroke="#D4AF37" strokeWidth="1.5" className="animate-goldPulse" />
        <text
          x="200"
          y="195"
          textAnchor="middle"
          className="fill-[#D4AF37]"
          style={{ fontSize: "28px", fontWeight: 700, fontFamily: "var(--font-geist-mono, monospace)" }}
        >
          XOOP
        </text>
        <text
          x="200"
          y="214"
          textAnchor="middle"
          className="fill-slate-400"
          style={{ fontSize: "9px", letterSpacing: "0.15em", fontFamily: "var(--font-geist-mono, monospace)" }}
        >
          REPUTATION
        </text>
      </svg>
    </div>
  );
}

export default function WelcomePage() {
  return (
    <div className="min-h-screen bg-[#030712] text-slate-100 font-sans selection:bg-[#D4AF37] selection:text-[#030712]">
      {/* NAV */}
      <header className="sticky top-0 z-40 border-b border-[#1F2937]/60 bg-[#030712]/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-6 py-4">
          {/* Left cluster: wordmark, parent badge, login, and request access all live here per the requested layout */}
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="font-mono text-lg font-extrabold tracking-widest text-[#D4AF37]">
                XOOP
              </span>
              <span className="hidden rounded-full border border-[#1F2937] bg-[#060B18] px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-slate-400 sm:inline-block">
                by Onlyne Reputation
              </span>
            </div>

            <Link
              href="/login"
              className="font-mono text-xs font-bold uppercase tracking-wider text-slate-300 transition-colors hover:text-[#D4AF37]"
            >
              Login
            </Link>

            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#D4AF37]/40 bg-[#D4AF37]/10 px-3 py-1.5 font-mono text-xs font-bold uppercase tracking-wider text-[#D4AF37] transition-colors hover:bg-[#D4AF37]/20"
            >
              <Mail className="h-3.5 w-3.5" />
              Request Access
            </a>
          </div>
        </div>
      </header>

      {/* HERO */}
      <section className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-12 px-6 py-16 md:grid-cols-2 md:py-24">
        <Reveal>
          <p className="mb-4 font-mono text-xs uppercase tracking-[0.2em] text-[#D4AF37]/80">
            eXecutive Online Opinion &amp; Perception
          </p>
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-slate-50 sm:text-5xl">
            One clear view of how the world sees your company.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-relaxed text-slate-400">
            XOOP continuously gathers what&apos;s being said about your company across the web
            and turns it into a single, understandable picture of your reputation — sentiment,
            risk, and trends in one place, instead of scattered across dozens of sources.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="inline-flex items-center gap-2 rounded-lg bg-[#D4AF37] px-5 py-3 text-sm font-bold uppercase tracking-wider text-[#030712] transition-colors hover:bg-[#F3C63F]"
            >
              Request Access
              <ArrowRight className="h-4 w-4" />
            </a>
            <Link
              href="/login"
              className="inline-flex items-center gap-2 rounded-lg border border-[#1F2937] px-5 py-3 text-sm font-bold uppercase tracking-wider text-slate-300 transition-colors hover:border-[#D4AF37]/50 hover:text-[#D4AF37]"
            >
              Existing client login
            </Link>
          </div>
          <p className="mt-4 text-xs text-slate-500">
            XOOP is a closed-loop platform for onboarded clients. New accounts are set up by our
            team — reach out at{" "}
            <a href={`mailto:${CONTACT_EMAIL}`} className="text-slate-400 underline decoration-dotted hover:text-[#D4AF37]">
              {CONTACT_EMAIL}
            </a>
            .
          </p>
        </Reveal>

        <Reveal delayMs={150}>
          <HeroVisual />
        </Reveal>
      </section>

      {/* HOW IT WORKS */}
      <section className="border-t border-[#1F2937]/60 bg-[#060B18]/40 py-20">
        <div className="mx-auto max-w-6xl px-6">
          <Reveal>
            <div className="mb-12 max-w-2xl">
              <h2 className="text-2xl font-bold text-slate-50 sm:text-3xl">How XOOP works</h2>
              <p className="mt-3 text-sm leading-relaxed text-slate-400">
                No dashboards to babysit and no manual searching. XOOP does the reading so your
                team can focus on the response.
              </p>
            </div>
          </Reveal>

          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {[
              {
                icon: Radar,
                title: "Collect",
                copy: "XOOP continuously watches news, articles, and other public coverage for mentions of your company and executives.",
              },
              {
                icon: Sparkles,
                title: "Understand",
                copy: "Each mention is read and classified — is the tone positive, negative, or neutral, and what topic is it actually about?",
              },
              {
                icon: ShieldAlert,
                title: "Detect",
                copy: "Emerging risks and shifting narratives are flagged early, so nothing critical gets buried in the noise.",
              },
              {
                icon: LayoutDashboard,
                title: "Unify",
                copy: "Everything rolls up into one reputation view — a single place to see where you stand and how it's moving.",
              },
            ].map((step, i) => (
              <Reveal key={step.title} delayMs={i * 100}>
                <div className="card-premium h-full rounded-2xl border border-[#1F2937] bg-[#060B18] p-6">
                  <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-[#D4AF37]/30 bg-[#D4AF37]/10">
                    <step.icon className="h-5 w-5 text-[#D4AF37]" />
                  </div>
                  <h3 className="font-mono text-xs font-bold uppercase tracking-wider text-slate-200">
                    {i + 1}. {step.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-400">{step.copy}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="border-t border-[#1F2937]/60 py-20">
        <div className="mx-auto max-w-6xl px-6">
          <Reveal>
            <h2 className="mb-12 text-2xl font-bold text-slate-50 sm:text-3xl">
              What you get
            </h2>
          </Reveal>

          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            {[
              {
                icon: LayoutDashboard,
                title: "Unified reputation view",
                copy: "A single score and summary that pulls together everything being said about your company, updated as new coverage comes in.",
              },
              {
                icon: Activity,
                title: "Sentiment & topic tracking",
                copy: "See not just how you're being talked about, but what specifically is driving the conversation.",
              },
              {
                icon: ShieldAlert,
                title: "Risk & alert detection",
                copy: "Get flagged on developing issues — critical coverage, negative narratives, or unusual spikes in attention.",
              },
              {
                icon: TrendingUp,
                title: "Trend visibility over time",
                copy: "Track how sentiment and reputation move over weeks and months, not just a single point-in-time snapshot.",
              },
            ].map((f, i) => (
              <Reveal key={f.title} delayMs={i * 80}>
                <div className="card-premium flex gap-4 rounded-2xl border border-[#1F2937] bg-[#060B18] p-6">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[#D4AF37]/30 bg-[#D4AF37]/10">
                    <f.icon className="h-5 w-5 text-[#D4AF37]" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-100">{f.title}</h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-slate-400">{f.copy}</p>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* PARENT COMPANY */}
      <section className="border-t border-[#1F2937]/60 bg-[#060B18]/40 py-16">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <Reveal>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">
              Built by
            </p>
            <h2 className="mt-2 text-xl font-bold text-slate-100">Onlyne Reputation</h2>
            <p className="mt-3 text-sm leading-relaxed text-slate-400">
              XOOP is Onlyne Reputation&apos;s reputation intelligence product — the same team
              that supports our clients&apos; broader reputation management work builds and
              operates the platform behind it.
            </p>
          </Reveal>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="border-t border-[#1F2937]/60 py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-3 px-6 text-center">
          <span className="font-mono text-sm font-bold tracking-widest text-[#D4AF37]">
            XOOP
          </span>
          <p className="text-xs text-slate-500">
            A product of Onlyne Reputation ·{" "}
            <a href={`mailto:${CONTACT_EMAIL}`} className="text-slate-400 underline decoration-dotted hover:text-[#D4AF37]">
              {CONTACT_EMAIL}
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
