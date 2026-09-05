"use client";

import React, { useRef, useState } from "react";
import Link from "next/link";
import { Unbounded, Sora, JetBrains_Mono } from "next/font/google";
import { motion, useScroll, useTransform, AnimatePresence } from "framer-motion";
import {
  ArrowRight,
  Mail,
  Menu,
  X,
  Activity,
  ShieldAlert,
  TrendingUp,
  LayoutDashboard,
} from "lucide-react";
import { AnimatedGrid } from "@/components/landing/AnimatedGrid";
import { SpotlightCard } from "@/components/landing/SpotlightCard";
import { PipelineBeams } from "@/components/landing/PipelineBeams";
import { BorderBeam } from "@/components/landing/BorderBeam";
import { ShimmerBadge } from "@/components/landing/ShimmerBadge";
import { MagneticButton } from "@/components/landing/MagneticButton";
import { Reveal, RevealGroup, RevealItem } from "@/components/landing/Reveal";

const CONTACT_EMAIL = "contact@onlynereputation.com";

/**
 * Font stacks are scoped to this landing page only (via the wrapper div's
 * className below) — layout.tsx and the authenticated app keep their own
 * fonts untouched.
 */
const display = Unbounded({
  subsets: ["latin"],
  weight: ["500", "700", "800"],
  variable: "--font-landing-display",
});
const body = Sora({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-landing-body",
});
const dataMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-landing-mono",
});

/**
 * Hero visual: mentions land as points, sweep past a radar arc, and resolve
 * into the risk score — the same collect -> score -> alert loop XOOP runs,
 * shown rather than described. This is the one place the accent gradient
 * (Solar Flare: #FF5E00 -> #FFB703) is used at any size.
 */
function HeroVisual() {
  const nodes = [
    { x: 60, y: 95, delay: "0s" },
    { x: 245, y: 80, delay: "0.18s" },
    { x: 252, y: 215, delay: "0.36s" },
    { x: 150, y: 262, delay: "0.54s" },
    { x: 52, y: 200, delay: "0.72s" },
  ];

  return (
    <div className="relative mx-auto aspect-square w-full max-w-[min(90vw,26rem)]">
      <div className="absolute inset-0 rounded-full bg-[radial-gradient(circle_at_center,rgba(255,94,0,0.16),transparent_65%)] blur-2xl" />
      <svg viewBox="0 0 300 300" className="relative h-full w-full overflow-visible">
        <defs>
          <linearGradient id="flareGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FF5E00" />
            <stop offset="100%" stopColor="#FFB703" />
          </linearGradient>
        </defs>

        <circle cx="150" cy="150" r="130" fill="none" stroke="#27272a" strokeWidth="1" />
        <circle cx="150" cy="150" r="95" fill="none" stroke="#27272a" strokeWidth="1" />

        <path
          d="M150 150 L150 20 A130 130 0 0 1 280 150 Z"
          fill="none"
          stroke="url(#flareGrad)"
          strokeWidth="1.6"
          opacity="0.22"
          className="origin-[150px_150px] animate-flareSweep"
        />

        {nodes.map((n, i) => (
          <circle
            key={i}
            cx={n.x}
            cy={n.y}
            r="5"
            fill="url(#flareGrad)"
            className="animate-nodeIn"
            style={{ animationDelay: n.delay }}
          />
        ))}

        <circle cx="150" cy="150" r="48" fill="#09090b" stroke="#3f3f46" strokeWidth="1" />
        <text
          x="150"
          y="160"
          textAnchor="middle"
          fill="url(#flareGrad)"
          style={{ fontSize: "34px", fontWeight: 600, fontFamily: "var(--font-landing-mono)" }}
        >
          74
        </text>
        <text
          x="150"
          y="181"
          textAnchor="middle"
          className="fill-zinc-500"
          style={{ fontSize: "9px", letterSpacing: "1.5px", fontFamily: "var(--font-landing-mono)" }}
        >
          RISK SCORE
        </text>

        <g className="animate-clusterTag">
          <rect x="95" y="235" width="110" height="20" rx="10" fill="#18181b" stroke="#27272a" />
          <text
            x="150"
            y="248"
            textAnchor="middle"
            fill="#9CA1AC"
            style={{ fontSize: "9px", fontFamily: "var(--font-landing-mono)" }}
          >
            +3 new narrative
          </text>
        </g>
      </svg>
    </div>
  );
}

const navLinkClass =
  "font-[family-name:var(--font-landing-mono)] text-xs font-bold uppercase tracking-wider text-zinc-400 transition-colors hover:text-white";

function Nav() {
  const [open, setOpen] = useState(false);

  return (
    <div className="sticky top-3 z-40 mx-auto max-w-5xl px-3 sm:top-4 sm:px-4">
      <header className="relative rounded-2xl border border-zinc-800 bg-zinc-950/80 shadow-[0_8px_30px_rgba(0,0,0,0.4)] backdrop-blur-xl">
        <div className="flex items-center justify-between px-4 py-3 sm:px-5">
          <span className="font-[family-name:var(--font-landing-mono)] text-lg font-bold tracking-widest text-[#FF5E00]">
            XOOP
          </span>

          {/* Desktop actions */}
          <div className="hidden items-center gap-5 sm:flex">
            <Link href="/login" className={navLinkClass}>
              Login
            </Link>
            <MagneticButton
              as={motion.a}
              href={`mailto:${CONTACT_EMAIL}`}
              className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-2 font-[family-name:var(--font-landing-mono)] text-xs font-bold uppercase tracking-wider text-zinc-950"
            >
              <Mail className="h-3.5 w-3.5" />
              Request Access
            </MagneticButton>
          </div>

          {/* Mobile menu toggle */}
          <button
            type="button"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="flex h-11 w-11 items-center justify-center rounded-xl border border-zinc-800 text-zinc-300 sm:hidden"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        <AnimatePresence>
          {open && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 32 }}
              className="overflow-hidden sm:hidden"
            >
              <div className="flex flex-col gap-3 border-t border-zinc-800 px-4 py-4">
                <Link href="/login" className={`${navLinkClass} py-2`} onClick={() => setOpen(false)}>
                  Login
                </Link>
                <a
                  href={`mailto:${CONTACT_EMAIL}`}
                  className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-white px-4 py-3 font-[family-name:var(--font-landing-mono)] text-xs font-bold uppercase tracking-wider text-zinc-950"
                >
                  <Mail className="h-3.5 w-3.5" />
                  Request Access
                </a>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </header>
    </div>
  );
}

function Hero() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ["start start", "end start"] });
  const gridY = useTransform(scrollYProgress, [0, 1], ["0%", "18%"]);
  const visualY = useTransform(scrollYProgress, [0, 1], ["0%", "-12%"]);
  const textY = useTransform(scrollYProgress, [0, 1], ["0%", "8%"]);

  return (
    <section ref={sectionRef} className="relative overflow-hidden">
      <motion.div style={{ y: gridY }}>
        <AnimatedGrid />
      </motion.div>
      <div className="relative mx-auto grid max-w-6xl grid-cols-1 items-center gap-[clamp(2.5rem,6vw,4rem)] px-[clamp(1.25rem,4vw,3rem)] py-[clamp(5rem,14vw,9rem)] md:grid-cols-2">
        <motion.div style={{ y: textY }}>
          <Reveal>
            <p className="mb-5 font-[family-name:var(--font-landing-mono)] text-xs uppercase tracking-[0.2em] text-[#FF5E00]/80">
              eXecutive Online Opinion &amp; Perception
            </p>
            <h1 className="text-balance font-[family-name:var(--font-landing-display)] font-extrabold leading-[1.05] text-[clamp(2.25rem,4vw+1rem,4.25rem)]">
              Your reputation, read the moment it changes.
            </h1>
            <p className="mt-6 max-w-lg text-[clamp(0.95rem,0.4vw+0.85rem,1.05rem)] leading-relaxed text-zinc-400">
              XOOP continuously gathers what&apos;s being said about your company across the web
              and turns it into a single, understandable picture of your reputation — sentiment,
              risk, and trends in one place, instead of scattered across dozens of sources.
            </p>
            <div className="mt-10 flex flex-col gap-4 min-[400px]:flex-row min-[400px]:flex-wrap min-[400px]:items-center">
              <MagneticButton
                as={motion.a}
                href={`mailto:${CONTACT_EMAIL}`}
                whileTap={{ scale: 0.96 }}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#FF5E00] px-5 py-3.5 text-sm font-bold uppercase tracking-wider text-[#1A0900]"
              >
                Request Access
                <ArrowRight className="h-4 w-4" />
              </MagneticButton>
              <Link
                href="/login"
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-zinc-800 px-5 py-3.5 text-sm font-bold uppercase tracking-wider text-zinc-400 transition-colors hover:border-zinc-700 hover:text-white"
              >
                Existing client login
              </Link>
            </div>
            <p className="mt-6 text-xs text-zinc-500">
              XOOP is a closed-loop platform for onboarded clients. New accounts are set up by our
              team — reach out at{" "}
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-zinc-400 underline decoration-dotted hover:text-[#FF5E00]">
                {CONTACT_EMAIL}
              </a>
              .
            </p>
          </Reveal>
        </motion.div>

        <motion.div style={{ y: visualY }}>
          <Reveal>
            <HeroVisual />
          </Reveal>
        </motion.div>
      </div>
    </section>
  );
}

const features = [
  {
    icon: LayoutDashboard,
    title: "Unified reputation view",
    copy: "A single score and summary that pulls together everything being said about your company, updated as new coverage comes in.",
    span: "lg:col-span-2",
  },
  {
    icon: Activity,
    title: "Sentiment & topic tracking",
    copy: "See not just how you're being talked about, but what's driving the conversation.",
    span: "",
  },
  {
    icon: ShieldAlert,
    title: "Risk & alert detection",
    copy: "Get flagged on developing issues — critical coverage, negative narratives, or unusual spikes in attention.",
    span: "",
  },
  {
    icon: TrendingUp,
    title: "Trend visibility over time",
    copy: "Track how sentiment and reputation move over weeks and months, not just a single point-in-time snapshot.",
    span: "lg:col-span-2",
  },
];

export default function WelcomePage() {
  return (
    <div
      className={`${display.variable} ${body.variable} ${dataMono.variable} min-h-screen overflow-x-hidden bg-zinc-950 text-zinc-50 font-[family-name:var(--font-landing-body)] selection:bg-[#FF5E00] selection:text-zinc-950`}
    >
      <Nav />
      <Hero />

      {/* PIPELINE — how mentions become a score, shown as flowing data */}
      <section className="border-t border-zinc-900 bg-zinc-950 py-[clamp(4rem,10vw,7rem)]">
        <div className="mx-auto max-w-6xl px-[clamp(1.25rem,4vw,3rem)]">
          <Reveal>
            <div className="mb-4 max-w-2xl">
              <h2 className="text-balance font-[family-name:var(--font-landing-display)] font-bold text-[clamp(1.75rem,2vw+1.25rem,2.5rem)]">
                How mentions become a score
              </h2>
              <p className="mt-4 text-sm leading-relaxed text-zinc-400">
                No dashboards to babysit and no manual searching. Every source XOOP watches feeds
                the same pipeline, continuously.
              </p>
            </div>
          </Reveal>
          <Reveal>
            <PipelineBeams />
          </Reveal>
        </div>
      </section>

      {/* BENTO — feature grid with mouse-tracking spotlight borders */}
      <section className="border-t border-zinc-900 py-[clamp(4rem,10vw,7rem)]">
        <div className="mx-auto max-w-6xl px-[clamp(1.25rem,4vw,3rem)]">
          <Reveal>
            <h2 className="mb-12 text-balance font-[family-name:var(--font-landing-display)] font-bold text-[clamp(1.75rem,2vw+1.25rem,2.5rem)] sm:mb-16">
              What you get
            </h2>
          </Reveal>

          <RevealGroup className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <RevealItem key={f.title} className={f.span}>
                <SpotlightCard className="h-full">
                  <div className="flex gap-4 p-5 sm:p-6">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[#FF5E00]/30 bg-[#FF5E00]/10">
                      <f.icon className="h-5 w-5 text-[#FF5E00]" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold tracking-tight text-zinc-50">{f.title}</h3>
                      <p className="mt-1.5 text-sm leading-relaxed text-zinc-400">{f.copy}</p>
                    </div>
                  </div>
                </SpotlightCard>
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </section>

      {/* FINAL CTA — border-beam card */}
      <section className="border-t border-zinc-900 py-[clamp(4rem,10vw,7rem)]">
        <div className="mx-auto max-w-3xl px-[clamp(1.25rem,4vw,3rem)]">
          <Reveal>
            <div className="relative overflow-hidden rounded-3xl border border-zinc-800 bg-zinc-900/60 p-[clamp(2rem,6vw,3.5rem)] text-center">
              <BorderBeam duration={7} />
              <BorderBeam duration={7} />
              <div className="relative">
                <div className="mb-5 flex justify-center">
                  <ShimmerBadge>Now onboarding Q1 clients</ShimmerBadge>
                </div>
                <h2 className="text-balance font-[family-name:var(--font-landing-display)] font-bold text-[clamp(1.75rem,2vw+1.25rem,2.5rem)]">
                  See your score before it becomes a headline.
                </h2>
                <p className="mx-auto mt-4 max-w-md text-sm leading-relaxed text-zinc-400">
                  Request access and we&apos;ll walk you through what XOOP is already tracking for
                  companies like yours.
                </p>
                <MagneticButton
                  as={motion.a}
                  href={`mailto:${CONTACT_EMAIL}`}
                  whileTap={{ scale: 0.96 }}
                  className="mt-8 inline-flex items-center justify-center gap-2 rounded-lg bg-[#FF5E00] px-6 py-3.5 text-sm font-bold uppercase tracking-wider text-[#1A0900]"
                >
                  Request Access
                  <ArrowRight className="h-4 w-4" />
                </MagneticButton>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* PARENT COMPANY */}
      <section className="border-t border-zinc-900 bg-zinc-950 py-[clamp(3.5rem,8vw,6rem)]">
        <div className="mx-auto max-w-3xl px-[clamp(1.25rem,4vw,3rem)] text-center">
          <Reveal>
            <p className="font-[family-name:var(--font-landing-mono)] text-[10px] uppercase tracking-[0.2em] text-zinc-500">
              Built by
            </p>
            <h2 className="mt-3 font-[family-name:var(--font-landing-display)] text-xl font-bold">
              Onlyne Reputation
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-zinc-400">
              XOOP is Onlyne Reputation&apos;s reputation intelligence product — the same team
              that supports our clients&apos; broader reputation management work builds and
              operates the platform behind it.
            </p>
          </Reveal>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="border-t border-zinc-900 py-10 sm:py-12">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-3 px-[clamp(1.25rem,4vw,3rem)] text-center">
          <span className="font-[family-name:var(--font-landing-mono)] text-sm font-bold tracking-widest text-[#FF5E00]">
            XOOP
          </span>
          <p className="text-xs text-zinc-500">
            A product of Onlyne Reputation ·{" "}
            <a href={`mailto:${CONTACT_EMAIL}`} className="text-zinc-400 underline decoration-dotted hover:text-[#FF5E00]">
              {CONTACT_EMAIL}
            </a>
          </p>
        </div>
      </footer>

      <style jsx global>{`
        @keyframes nodeIn {
          0% {
            opacity: 0;
            transform: scale(0.4);
          }
          18% {
            opacity: 1;
            transform: scale(1);
          }
          75% {
            opacity: 1;
            transform: scale(1);
          }
          92%,
          100% {
            opacity: 0;
          }
        }
        @keyframes flareSweep {
          to {
            transform: rotate(360deg);
          }
        }
        @keyframes clusterTag {
          0%,
          55% {
            opacity: 0;
            transform: translateY(4px);
          }
          68% {
            opacity: 1;
            transform: translateY(0);
          }
          88% {
            opacity: 1;
          }
          100% {
            opacity: 0;
          }
        }
        @keyframes gridPan {
          from {
            background-position: 0 0, 0 0;
          }
          to {
            background-position: 64px 64px, 64px 64px;
          }
        }
        @keyframes borderBeam {
          from {
            offset-distance: 0%;
          }
          to {
            offset-distance: 100%;
          }
        }
        @keyframes shimmerText {
          from {
            background-position: 200% 0;
          }
          to {
            background-position: -200% 0;
          }
        }
        .animate-nodeIn {
          animation: nodeIn 3.2s cubic-bezier(0.16, 1, 0.3, 1) infinite;
        }
        .animate-flareSweep {
          animation: flareSweep 3.2s linear infinite;
        }
        .animate-clusterTag {
          animation: clusterTag 3.2s cubic-bezier(0.16, 1, 0.3, 1) infinite;
        }
        .animate-gridPan {
          animation: gridPan 14s linear infinite;
        }
        .animate-borderBeam {
          animation: borderBeam linear infinite;
        }
        .animate-borderBeam:nth-of-type(2) {
          animation-delay: -3.5s;
        }
        .animate-shimmerText {
          animation: shimmerText 2.5s linear infinite;
        }
        @media (prefers-reduced-motion: reduce) {
          .animate-nodeIn,
          .animate-flareSweep,
          .animate-clusterTag,
          .animate-gridPan,
          .animate-borderBeam,
          .animate-shimmerText {
            animation: none !important;
          }
        }
      `}</style>
    </div>
  );
}
