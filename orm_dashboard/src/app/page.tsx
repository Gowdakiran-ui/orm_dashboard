"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Fraunces, Inter } from "next/font/google";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Mail, Menu, X } from "lucide-react";
import { MagneticButton } from "@/components/landing/MagneticButton";
import { Reveal, RevealGroup, RevealItem } from "@/components/landing/Reveal";

const CONTACT_EMAIL = "contact@onlynereputation.com";

/**
 * Redesign (2026-09-23): same stack as before (Next.js App Router, React,
 * Tailwind, framer-motion) -- new visual design (dark navy/teal editorial
 * look, Fraunces serif + Inter body) approved via a Claude artifact
 * reference. Font stacks are scoped to this landing page only (via the
 * wrapper div's className below) -- layout.tsx and the authenticated app
 * keep their own fonts untouched.
 *
 * Colors are literal hex values in every Tailwind className below (never
 * interpolated via a JS template string into an arbitrary-value class,
 * e.g. `text-[${x}]`) -- Tailwind's compiler scans source statically for
 * class name strings, so an interpolated class is invisible to it and
 * silently produces no CSS. Dynamic per-row colors (mock chart data below)
 * use inline `style` instead, which has no such restriction.
 */
const display = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-landing-display",
});
const body = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-landing-body",
});

const navLinkClass = "text-sm text-[#93A6C7] transition-colors hover:text-white";

function Nav() {
  const [open, setOpen] = useState(false);

  return (
    <nav
      className="sticky top-0 z-40 border-b border-[#163F6E] bg-[#04213F]/85 backdrop-blur-md"
      style={{ paddingTop: "env(safe-area-inset-top, 0px)" }}
    >
      <div className="mx-auto flex h-[72px] max-w-6xl items-center justify-between px-5 sm:px-7">
        <div className="flex items-center gap-2.5 font-[family-name:var(--font-landing-display)] text-xl font-semibold">
          <span className="h-[9px] w-[9px] rounded-full bg-[#2FD9C4] shadow-[0_0_0_4px_rgba(47,217,196,0.16)]" />
          XOOP
        </div>

        <div className="hidden items-center gap-8 sm:flex">
          <a href="#framework" className={navLinkClass}>How it works</a>
          <a href="#preview" className={navLinkClass}>Product</a>
          <a href="#features" className={navLinkClass}>Features</a>
          <a href="#benefits" className={navLinkClass}>Benefits</a>
        </div>

        <div className="hidden items-center gap-2.5 sm:flex">
          <Link
            href="/login"
            className="rounded-lg border border-[#1E4C84] px-[19px] py-2.5 text-sm font-medium text-white transition-colors hover:border-[#2FD9C4] hover:text-[#2FD9C4]"
          >
            Sign in
          </Link>
          <MagneticButton
            as={motion.a}
            href={`mailto:${CONTACT_EMAIL}`}
            className="rounded-lg bg-[#2FD9C4] px-5 py-2.5 text-sm font-semibold text-[#06211C] transition-transform"
          >
            Request access
          </MagneticButton>
        </div>

        <button
          type="button"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className="flex h-11 w-11 items-center justify-center rounded-lg border border-[#1E4C84] text-white sm:hidden"
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
            className="overflow-hidden border-t border-[#163F6E] sm:hidden"
          >
            <div className="flex flex-col gap-1 px-5 py-4">
              <a href="#framework" className={`${navLinkClass} py-2.5`} onClick={() => setOpen(false)}>How it works</a>
              <a href="#preview" className={`${navLinkClass} py-2.5`} onClick={() => setOpen(false)}>Product</a>
              <a href="#features" className={`${navLinkClass} py-2.5`} onClick={() => setOpen(false)}>Features</a>
              <a href="#benefits" className={`${navLinkClass} py-2.5`} onClick={() => setOpen(false)}>Benefits</a>
              <div className="mt-3 flex flex-col gap-3">
                <Link
                  href="/login"
                  className="rounded-lg border border-[#1E4C84] px-4 py-3 text-center text-sm font-medium text-white"
                >
                  Sign in
                </Link>
                <a
                  href={`mailto:${CONTACT_EMAIL}`}
                  className="rounded-lg bg-[#2FD9C4] px-4 py-3 text-center text-sm font-semibold text-[#06211C]"
                >
                  Request access
                </a>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
}

function Hero() {
  return (
    <header className="pb-16 pt-[88px]">
      <div className="mx-auto max-w-6xl px-5 sm:px-7">
        <Reveal>
          <div className="mb-[22px] inline-flex items-center gap-2 text-[0.86rem] font-medium text-[#2FD9C4]">
            <span className="relative flex h-[7px] w-[7px]">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#2FD9C4] opacity-60" />
              <span className="relative inline-flex h-[7px] w-[7px] rounded-full bg-[#2FD9C4]" />
            </span>
            Reputation Intelligence, not just monitoring
          </div>

          <h1 className="max-w-[16ch] text-balance font-[family-name:var(--font-landing-display)] font-medium leading-[1.08] text-white text-[clamp(2.3rem,5vw,3.6rem)]">
            We don&apos;t just tell you what happened. We tell you{" "}
            <em className="not-italic italic text-[#2FD9C4]">why it matters</em> and what to do next.
          </h1>

          <p className="mt-6 max-w-[58ch] text-[1.14rem] leading-relaxed text-[#93A6C7]">
            Listening and monitoring tools show you the noise. XOOP connects conversations,
            behaviour, search and stakeholder signals into one picture — so your team can act
            on a shift before it becomes a headline, not after.
          </p>

          <div className="mt-9 flex flex-wrap gap-3.5">
            <MagneticButton
              as={motion.a}
              href={`mailto:${CONTACT_EMAIL}`}
              whileTap={{ scale: 0.96 }}
              className="inline-flex items-center gap-2 rounded-lg bg-[#2FD9C4] px-5 py-3.5 text-sm font-semibold text-[#06211C]"
            >
              <Mail className="h-4 w-4" />
              Request access
            </MagneticButton>
            <a
              href="#preview"
              className="inline-flex items-center gap-2 rounded-lg border border-[#1E4C84] px-5 py-3.5 text-sm font-medium text-white transition-colors hover:border-[#2FD9C4] hover:text-[#2FD9C4]"
            >
              See the product ↓
            </a>
          </div>

          <p className="mt-6 text-xs text-[#5D719A]">
            XOOP is a closed-loop platform for onboarded clients. New accounts are set up by our
            team — reach out at{" "}
            <a href={`mailto:${CONTACT_EMAIL}`} className="text-[#93A6C7] underline decoration-dotted">
              {CONTACT_EMAIL}
            </a>
            .
          </p>
        </Reveal>

        <Reveal>
          <div className="mt-16 grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-[#163F6E] bg-[#163F6E] sm:grid-cols-2">
            <div className="bg-[#0B2D54] p-8">
              <div className="text-[0.8rem] text-[#5D719A]">Monitoring &amp; listening tools</div>
              <div className="mt-2.5 font-[family-name:var(--font-landing-display)] text-[1.2rem] font-medium text-white">
                Tell you what happened.
              </div>
            </div>
            <div className="bg-[#143D6E] p-8">
              <div className="text-[0.8rem] text-[#5D719A]">XOOP</div>
              <div className="mt-2.5 font-[family-name:var(--font-landing-display)] text-[1.2rem] font-medium text-[#2FD9C4]">
                Tells you why it happened, what&apos;s likely next, and what to do about it.
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </header>
  );
}

const framework = [
  { word: "What", title: "What's actually happening right now", copy: "Every signal across every channel resolved into one clear read — a rising risk, a sentiment shift, an emerging alert — not a wall of raw mentions to sort through yourself." },
  { word: "Where", title: "Where the conversation is happening", copy: "Press, social, forums, video — broken out by source, so you know immediately if it's one contained post or breaking across five channels at once." },
  { word: "Why", title: "Why it's happening", copy: "The real story, topic, or stakeholder driving the shift — root-cause context tied to actual coverage, not just a number that moved without explanation." },
  { word: "When", title: "When it started, and where it's heading", copy: "Trend direction over time, not a static score — improving, stable, or declining, and since when, so you can act before it compounds." },
  { word: "Whom", title: "Whom it affects", copy: "Reputation risk is rarely abstract. We name the executive, the stakeholder, or the specific story actually carrying the coverage." },
  { word: "How", title: "How to respond", copy: "A clear read on what's driving the number and what needs attention first — so your team acts on signal, not on noise." },
];

function SectionHead({ title, copy }: { title: string; copy: string }) {
  return (
    <div className="mb-[52px] max-w-[62ch]">
      <h2 className="text-balance font-[family-name:var(--font-landing-display)] font-medium text-white text-[clamp(1.7rem,3.4vw,2.4rem)]">
        {title}
      </h2>
      <p className="mt-3.5 text-[1.03rem] leading-relaxed text-[#93A6C7]">{copy}</p>
    </div>
  );
}

function Framework() {
  return (
    <section id="framework" className="border-t border-[#163F6E] py-24">
      <div className="mx-auto max-w-6xl px-5 sm:px-7">
        <Reveal>
          <SectionHead
            title="Every reputation problem has six real questions. We answer all of them."
            copy="Not a feed of mentions — a straight answer to the six questions your comms team actually has to answer for leadership, every time something moves."
          />
        </Reveal>

        <RevealGroup className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-[#163F6E] bg-[#163F6E] sm:grid-cols-2 lg:grid-cols-3">
          {framework.map((f) => (
            <RevealItem key={f.word}>
              <div className="h-full min-h-[190px] bg-[#0B2D54] p-7 transition-colors hover:bg-[#0F3663]">
                <div className="mb-3.5 font-[family-name:var(--font-landing-display)] text-sm font-medium tracking-wide text-[#2FD9C4]">
                  {f.word}
                </div>
                <h3 className="mb-2.5 text-[1.14rem] font-medium leading-tight text-white">{f.title}</h3>
                <p className="text-[0.93rem] leading-relaxed text-[#93A6C7]">{f.copy}</p>
              </div>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  );
}

function MockPanel({ title, children, noPadding = false }: { title: string; children: React.ReactNode; noPadding?: boolean }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-[#163F6E] bg-[#0B2D54]">
      <div className="flex items-center gap-2 border-b border-[#163F6E] bg-[#0F3663] px-4 py-3">
        <span className="h-2 w-2 rounded-full bg-[#1E4C84]" />
        <span className="h-2 w-2 rounded-full bg-[#1E4C84]" />
        <span className="h-2 w-2 rounded-full bg-[#1E4C84]" />
        <span className="ml-1.5 text-[0.78rem] tracking-wide text-[#5D719A]">{title}</span>
      </div>
      <div className={noPadding ? "" : "p-5"}>{children}</div>
    </div>
  );
}

/**
 * Real product screenshots (Anthropic -- richest real data across this
 * project), captured live and supplied by the team, replacing the
 * illustrative mocks the v1 draft shipped with. `aspect` matches each
 * source image's own proportions so `object-cover` never crops into
 * meaningful content; `objectPosition` favors whichever edge (top for
 * stat-row panels, left/center for wide multi-column ones) keeps the real
 * subject matter in frame.
 */
function ScreenshotPanel({
  title,
  src,
  alt,
  aspect = "aspect-[16/10]",
  objectPosition = "top",
}: {
  title: string;
  src: string;
  alt: string;
  aspect?: string;
  objectPosition?: string;
}) {
  return (
    <MockPanel title={title} noPadding>
      <div className={`relative w-full ${aspect} overflow-hidden`}>
        {/* eslint-disable-next-line @next/next/no-img-element -- static
            marketing screenshots served from /public, not a page needing
            next/image's responsive-loader pipeline. */}
        <img src={src} alt={alt} className="absolute inset-0 h-full w-full object-cover" style={{ objectPosition }} />
      </div>
    </MockPanel>
  );
}

function ProductPreview() {
  return (
    <section id="preview" className="py-24">
      <div className="mx-auto max-w-6xl px-5 sm:px-7">
        <Reveal>
          <SectionHead title="Inside the platform" copy="A live look at how XOOP turns raw coverage into a decision." />
        </Reveal>

        <RevealGroup className="grid grid-cols-1 gap-[18px] lg:grid-cols-2">
          <RevealItem>
            <ScreenshotPanel
              title="BRAND EQUITY — OVERVIEW"
              src="/landing/brand-equity.png"
              alt="XOOP Brand Equity overview: reputation score, risk profile, sentiment, and competitive standing for a tracked client"
              aspect="aspect-[4/3]"
            />
          </RevealItem>
          <RevealItem>
            <ScreenshotPanel
              title="RISK CENTER — ACTIVE ALERTS"
              src="/landing/active-alerts.png"
              alt="XOOP Risk Center: total risk counts, active critical alerts, and the likelihood-by-impact risk matrix"
              aspect="aspect-[4/3]"
            />
          </RevealItem>
        </RevealGroup>
        <RevealGroup className="mt-[18px] grid grid-cols-1 gap-[18px] sm:grid-cols-2">
          <RevealItem>
            <ScreenshotPanel
              title="REAL-TIME INTELLIGENCE STREAM"
              src="/landing/intelligence-stream.png"
              alt="XOOP real-time brand ingest stream, showing matched coverage scored and tagged as it arrives across RSS, YouTube, Instagram, and Reddit"
              aspect="aspect-[4/3]"
            />
          </RevealItem>
          <RevealItem>
            <ScreenshotPanel
              title="COMPETITOR HEAD-TO-HEAD"
              src="/landing/competitor-radar.png"
              alt="XOOP competitor head-to-head radar comparing reputation, sentiment, risk containment, and share of voice"
              aspect="aspect-[4/3]"
            />
          </RevealItem>
        </RevealGroup>
        <RevealGroup className="mt-[18px] grid grid-cols-1">
          <RevealItem>
            <ScreenshotPanel
              title="PRODUCT COMPARE"
              src="/landing/product-compare.png"
              alt="XOOP Product Compare: two competing products benchmarked side by side on reputation, rank, risk, share of voice, and signature stories"
              aspect="aspect-[16/9]"
              objectPosition="top"
            />
          </RevealItem>
        </RevealGroup>

        <p className="mt-[18px] text-center text-[0.86rem] text-[#5D719A]">
          Real screenshots from the live platform, tracking Anthropic.
        </p>
      </div>
    </section>
  );
}

const featureRows = [
  { title: "Real-time, multi-channel monitoring", copy: "Press, RSS, social, video and forum coverage collected continuously across every client you manage, matched automatically to the right brand, executive, or competitor." },
  { title: "AI-scored sentiment and risk on every mention", copy: "Every piece of coverage is scored for sentiment and risk the moment it's ingested — so a single alarming article is never buried in a feed of routine mentions." },
  { title: "Executive reputation tracking", copy: "Individual leaders get their own reputation score, grade, and a plain-language explanation of what's actually driving it — not just a number with no context." },
  { title: "Competitor benchmarking", copy: "Share of voice, sentiment comparison, and topic ownership against every competitor you track — a real head-to-head, not a guess based on gut feel." },
  { title: "Automated risk alerts", copy: "Critical shifts surface immediately, scored and prioritised, instead of waiting for someone to notice a bad headline in their inbox." },
  { title: "One dashboard, every client", copy: "Switch between every brand your team manages from a single login — the same rigour applied consistently, account to account." },
];

function Features() {
  return (
    <section id="features" className="border-t border-[#163F6E] py-24">
      <div className="mx-auto max-w-6xl px-5 sm:px-7">
        <Reveal>
          <SectionHead title="What's under the hood" copy="Everything you need to move from &quot;we saw a mention&quot; to &quot;here's what we're doing about it.&quot;" />
        </Reveal>

        <RevealGroup className="flex flex-col">
          {featureRows.map((f, idx) => (
            <RevealItem key={f.title}>
              <div className={`grid grid-cols-1 items-baseline gap-2.5 py-8 sm:grid-cols-[2fr_3fr] sm:gap-10 ${idx > 0 ? "border-t border-[#163F6E]" : ""}`}>
                <h3 className="text-[1.28rem] font-medium text-white">{f.title}</h3>
                <p className="max-w-[56ch] text-[0.98rem] leading-relaxed text-[#93A6C7]">{f.copy}</p>
              </div>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  );
}

const benefitCells = [
  { title: "Spot a shift before it's a headline", copy: "Emerging issues, crisis signals, and stakeholder concerns surface while they're still manageable — not after a journalist has already called." },
  { title: "Walk into every client call with an answer", copy: "No more \"let me get back to you.\" What changed, why, and what's next is already on the dashboard when the question comes." },
  { title: "Prove the value of your comms work", copy: "A real, defensible reputation score your team can point to — trending in a direction you can explain, not a vague sense that things are \"going fine.\"" },
  { title: "Act on signal, not on noise", copy: "Stop scrolling raw mentions to guess what matters. The platform tells you what's worth your attention today, and what isn't." },
];

function Benefits() {
  return (
    <section id="benefits" className="border-t border-[#163F6E] bg-[#0B2D54] py-24">
      <div className="mx-auto max-w-6xl px-5 sm:px-7">
        <Reveal>
          <SectionHead title="What this actually changes for your team" copy="Not features for their own sake — the outcomes they're built for." />
        </Reveal>

        <RevealGroup className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-[#163F6E] bg-[#163F6E] sm:grid-cols-2">
          {benefitCells.map((b) => (
            <RevealItem key={b.title}>
              <div className="h-full bg-[#0B2D54] p-8">
                <span className="mb-3.5 block font-[family-name:var(--font-landing-display)] text-2xl text-[#2FD9C4]">—</span>
                <h3 className="mb-2 text-[1.1rem] font-medium text-white">{b.title}</h3>
                <p className="text-[0.94rem] leading-relaxed text-[#93A6C7]">{b.copy}</p>
              </div>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  );
}

function FinalCTA() {
  return (
    <section className="py-[100px] text-center">
      <div className="mx-auto max-w-3xl px-5 sm:px-7">
        <Reveal>
          <span className="inline-flex items-center rounded-full border border-[#1E4C84] px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-[#93A6C7]">
            Now onboarding Q1 clients
          </span>
          <h2 className="mx-auto mt-5 max-w-[20ch] text-balance font-[family-name:var(--font-landing-display)] font-medium text-white text-[clamp(1.8rem,4vw,2.6rem)]">
            See what your reputation data has been trying to tell you.
          </h2>
          <p className="mt-4 text-[1.05rem] text-[#93A6C7]">Book a walkthrough with the team behind XOOP.</p>
          <div className="mt-8 flex justify-center">
            <MagneticButton
              as={motion.a}
              href={`mailto:${CONTACT_EMAIL}`}
              whileTap={{ scale: 0.96 }}
              className="inline-flex items-center gap-2 rounded-lg bg-[#2FD9C4] px-6 py-3.5 text-sm font-semibold text-[#06211C]"
            >
              <Mail className="h-4 w-4" />
              Request access
              <ArrowRight className="h-4 w-4" />
            </MagneticButton>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export default function WelcomePage() {
  return (
    <div
      className={`${display.variable} ${body.variable} min-h-screen overflow-x-hidden bg-[#04213F] font-[family-name:var(--font-landing-body)] text-white`}
    >
      <Nav />
      <Hero />
      <Framework />
      <ProductPreview />
      <Features />
      <Benefits />
      <FinalCTA />

      {/* PARENT COMPANY */}
      <section className="border-t border-[#163F6E] py-16">
        <div className="mx-auto max-w-3xl px-5 text-center sm:px-7">
          <Reveal>
            <p className="text-[10px] uppercase tracking-[0.2em] text-[#5D719A]">Built by</p>
            <h2 className="mt-3 font-[family-name:var(--font-landing-display)] text-xl font-medium text-white">
              Onlyne Reputation
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-[#93A6C7]">
              XOOP is Onlyne Reputation&apos;s reputation intelligence product — the same team
              that supports our clients&apos; broader reputation management work builds and
              operates the platform behind it.
            </p>
          </Reveal>
        </div>
      </section>

      {/* FOOTER */}
      <footer
        className="border-t border-[#163F6E] py-[34px]"
        style={{ paddingBottom: "calc(34px + env(safe-area-inset-bottom, 0px))" }}
      >
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 sm:px-7">
          <div className="flex items-center gap-2.5 font-[family-name:var(--font-landing-display)] text-[1.05rem] font-semibold">
            <span className="h-[9px] w-[9px] rounded-full bg-[#2FD9C4]" />
            XOOP
          </div>
          <p className="text-[0.82rem] text-[#5D719A]">
            A product of Onlyne Reputation ·{" "}
            <a href={`mailto:${CONTACT_EMAIL}`} className="text-[#93A6C7] underline decoration-dotted">
              {CONTACT_EMAIL}
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
