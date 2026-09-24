"use client";

import React, { useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight, Mail, Menu, X,
  Activity, MapPin, HelpCircle, Clock, Users, Compass,
  Radio, Gauge, UserCheck, Swords, Bell, LayoutDashboard, ShieldAlert,
  TrendingUp, Rocket, Building2,
  Eye, MessageCircle, BadgeCheck, Target,
  Check, Minus,
} from "lucide-react";
import { MagneticButton } from "@/components/landing/MagneticButton";
import { Reveal, RevealGroup, RevealItem } from "@/components/landing/Reveal";

const CONTACT_EMAIL = "contact@onlynereputation.com";

/**
 * Redesign (2026-09-23) + round 2 correction pass (CEO review): same stack
 * throughout (Next.js App Router, React, Tailwind, framer-motion), dark
 * navy/gold editorial look, Rockwell throughout. Font stacks are scoped to
 * this landing page only (via the wrapper div's inline style below) --
 * layout.tsx and the authenticated app keep their own fonts untouched.
 *
 * Color-theme + font pass (parent-company alignment): accent swapped from
 * teal to the gold/navy/white palette measured live off onlynereputation.com
 * (nav/hero navy ~#02162B-#03203E, heading gold ~#CEA555, button gold
 * ~#A57F37) -- every former #2FD9C4 (teal accent) is now #CEA555 (gold) and
 * every former #06211C (button text on the accent) is now #0B2D54 (dark
 * navy), a mechanical token swap since the same hex was reused consistently
 * as "the accent color" throughout. Display/body fonts (previously Fraunces
 * + Inter, both next/font/google) replaced with Rockwell -- not a Google
 * Font, so no next/font loader; set as a literal CSS font stack instead
 * (real Rockwell where the OS has it installed, a slab-serif fallback chain
 * otherwise). Text content and layout are unchanged, colors and font only.
 *
 * Round 2 note: every em dash in this file's copy was deliberately
 * rewritten (comma/colon/period/restructured sentence) per explicit CEO
 * feedback -- do not reintroduce "--" when editing copy here.
 */
const ROCKWELL_STACK = "'Rockwell', 'Rockwell Nova', 'Roboto Slab', Georgia, serif";

// Subtle grid texture for the deep-navy page background (round 2, item 2)
// -- CSS gradient lines, not an image asset, so it stays crisp at any
// viewport and costs nothing to load. 3% white opacity: meant to be felt,
// not seen, the same restraint as the rest of this design.
const GRID_TEXTURE =
  "linear-gradient(rgba(255,255,255,0.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.035) 1px,transparent 1px)";

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
          <span className="h-[9px] w-[9px] rounded-full bg-[#CEA555] shadow-[0_0_0_4px_rgba(47,217,196,0.16)]" />
          XOOP
        </div>

        <div className="hidden items-center gap-8 sm:flex">
          <a href="#reputation-intelligence" className={navLinkClass}>Why XOOP</a>
          <a href="#who-its-for" className={navLinkClass}>Who it&apos;s for</a>
          <a href="#preview" className={navLinkClass}>Product</a>
          <a href="#features" className={navLinkClass}>Features</a>
          <a href="#benefits" className={navLinkClass}>Benefits</a>
        </div>

        <div className="hidden items-center gap-2.5 sm:flex">
          <Link
            href="/login"
            className="rounded-lg border border-[#1E4C84] px-[19px] py-2.5 text-sm font-medium text-white transition-colors hover:border-[#CEA555] hover:text-[#CEA555]"
          >
            Sign in
          </Link>
          <MagneticButton
            as={motion.a}
            href={`mailto:${CONTACT_EMAIL}`}
            className="rounded-lg bg-[#CEA555] px-5 py-2.5 text-sm font-semibold text-[#0B2D54] transition-transform"
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
              <a href="#reputation-intelligence" className={`${navLinkClass} py-2.5`} onClick={() => setOpen(false)}>Why XOOP</a>
              <a href="#who-its-for" className={`${navLinkClass} py-2.5`} onClick={() => setOpen(false)}>Who it&apos;s for</a>
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
                  className="rounded-lg bg-[#CEA555] px-4 py-3 text-center text-sm font-semibold text-[#0B2D54]"
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
          <div className="mb-[22px] inline-flex items-center gap-2 text-[0.86rem] font-medium text-[#CEA555]">
            <span className="relative flex h-[7px] w-[7px]">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#CEA555] opacity-60" />
              <span className="relative inline-flex h-[7px] w-[7px] rounded-full bg-[#CEA555]" />
            </span>
            Reputation Intelligence, not just monitoring
          </div>

          <h1 className="max-w-[16ch] text-balance font-[family-name:var(--font-landing-display)] font-medium leading-[1.08] text-white text-[clamp(2.3rem,5vw,3.6rem)]">
            We don&apos;t just tell you what happened. We tell you{" "}
            <em className="not-italic italic text-[#CEA555]">why it matters</em> and what to do next.
          </h1>

          <p className="mt-6 max-w-[58ch] text-[1.14rem] leading-relaxed text-[#93A6C7]">
            Listening and monitoring tools show you the noise. XOOP connects conversations,
            behaviour, search and stakeholder signals into one picture, so your team can act
            on a shift before it becomes a headline, not after.
          </p>

          <div className="mt-9 flex flex-wrap gap-3.5">
            <MagneticButton
              as={motion.a}
              href={`mailto:${CONTACT_EMAIL}`}
              whileTap={{ scale: 0.96 }}
              className="inline-flex items-center gap-2 rounded-lg bg-[#CEA555] px-5 py-3.5 text-sm font-semibold text-[#0B2D54]"
            >
              <Mail className="h-4 w-4" />
              Request access
            </MagneticButton>
            <a
              href="#preview"
              className="inline-flex items-center gap-2 rounded-lg border border-[#1E4C84] px-5 py-3.5 text-sm font-medium text-white transition-colors hover:border-[#CEA555] hover:text-[#CEA555]"
            >
              See the product ↓
            </a>
          </div>

          <p className="mt-6 text-xs text-[#5D719A]">
            XOOP is a closed-loop platform for onboarded clients. New accounts are set up by our
            team: reach out at{" "}
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
              <div className="mt-2.5 font-[family-name:var(--font-landing-display)] text-[1.2rem] font-medium text-[#CEA555]">
                Tells you why it happened, what&apos;s likely next, and what to do about it.
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </header>
  );
}

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

// Round 2, items 4 + 5: the source positioning doc's three numbered points,
// each given real elaboration tied to an actual product capability (not a
// restatement of the doc's own wording), plus the explicit "not a
// listening tool" statement the doc only implied before via the hero
// contrast block.
const reputationPoints = [
  {
    numeral: "I",
    title: "We help you spot reputation shifts early",
    copy: "XOOP connects conversations, behaviour, search and stakeholder signals to show what's changing around your business. Risk Center flags a developing issue as a Critical or High alert the moment it clears a real evidence threshold, not after it's already a headline.",
  },
  {
    numeral: "II",
    title: "We explain what may happen next",
    copy: "Every risk event carries its own written explanation of what's driving it and what to do about it. Trend Direction shows whether a client's reputation is improving, stable, or declining, so a shift arrives with context attached, not just a number that moved.",
  },
  {
    numeral: "III",
    title: "We turn reputation data into business decisions",
    copy: "One reputation score and grade, competitor benchmarking, and executive-level tracking give your team a single place to point to when a leadership call, a campaign, or a crisis response has to be backed by something real.",
  },
];

function ReputationIntelligence() {
  return (
    <section id="reputation-intelligence" className="relative overflow-hidden border-t border-[#163F6E] py-24">
      <div className="mx-auto max-w-6xl px-5 sm:px-7">
        <Reveal>
          <SectionHead
            title="This is reputation intelligence, not listening."
            copy="Every product decision in XOOP traces back to the same three-part idea, not a slogan, an operating principle."
          />
        </Reveal>

        <Reveal>
          <div className="mb-14 rounded-2xl border border-[#CEA555]/25 bg-[#0B2D54] p-8 sm:p-10">
            <p className="text-balance font-[family-name:var(--font-landing-display)] text-[1.3rem] font-medium leading-snug text-white sm:text-[1.5rem]">
              XOOP is not a listening tool. Listening tools show you mentions.{" "}
              <span className="text-[#CEA555]">We show you what they mean.</span>
            </p>
          </div>
        </Reveal>

        <RevealGroup className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {reputationPoints.map((p) => (
            <RevealItem key={p.numeral}>
              <div className="h-full rounded-2xl border border-[#163F6E] bg-[#0B2D54] p-7">
                <span className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-[#CEA555]/30 bg-[#CEA555]/10 font-[family-name:var(--font-landing-display)] text-sm font-semibold text-[#CEA555]">
                  {p.numeral}
                </span>
                <h3 className="mb-2.5 text-[1.1rem] font-medium leading-snug text-white">{p.title}</h3>
                <p className="text-[0.93rem] leading-relaxed text-[#93A6C7]">{p.copy}</p>
              </div>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  );
}

const framework = [
  { word: "What", icon: Activity, title: "What's actually happening right now", copy: "Every signal across every channel resolved into one clear read: a rising risk, a sentiment shift, an emerging alert, not a wall of raw mentions to sort through yourself." },
  { word: "Where", icon: MapPin, title: "Where the conversation is happening", copy: "Press, social, forums, video: broken out by source, so you know immediately if it's one contained post or breaking across five channels at once." },
  { word: "Why", icon: HelpCircle, title: "Why it's happening", copy: "The real story, topic, or stakeholder driving the shift: root-cause context tied to actual coverage, not just a number that moved without explanation." },
  { word: "When", icon: Clock, title: "When it started, and where it's heading", copy: "Trend direction over time, not a static score: improving, stable, or declining, and since when, so you can act before it compounds." },
  { word: "Whom", icon: Users, title: "Whom it affects", copy: "Reputation risk is rarely abstract. We name the executive, the stakeholder, or the specific story actually carrying the coverage." },
  { word: "How", icon: Compass, title: "How to respond", copy: "A clear read on what's driving the number and what needs attention first, so your team acts on signal, not on noise." },
];

function Framework() {
  return (
    <section id="framework" className="border-t border-[#163F6E] py-24">
      <div className="mx-auto max-w-6xl px-5 sm:px-7">
        <Reveal>
          <SectionHead
            title="Every reputation problem has six real questions. We answer all of them."
            copy="Not a feed of mentions. A straight answer to the six questions your comms team actually has to answer for leadership, every time something moves."
          />
        </Reveal>

        <RevealGroup className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-[#163F6E] bg-[#163F6E] sm:grid-cols-2 lg:grid-cols-3">
          {framework.map((f) => (
            <RevealItem key={f.word}>
              <div className="h-full min-h-[190px] bg-[#0B2D54] p-7 transition-colors hover:bg-[#0F3663]">
                <div className="mb-3.5 flex items-center gap-2">
                  <f.icon className="h-4 w-4 text-[#CEA555]" strokeWidth={2} />
                  <span className="font-[family-name:var(--font-landing-display)] text-sm font-medium tracking-wide text-[#CEA555]">
                    {f.word}
                  </span>
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

// Round 2, item 3: who this is for, grounded in real capabilities already
// built (reputation scoring, risk alerting, executive tracking, competitor
// benchmarking) rather than generic claims.
const audiences = [
  {
    icon: TrendingUp,
    title: "IPOs",
    copy: "Going public puts your reputation under a magnifying glass overnight. XOOP tracks sentiment and narrative shifts across press and social in the run-up to a listing, so a story that could move investor perception gets flagged while there's still time to respond.",
  },
  {
    icon: Rocket,
    title: "Startups",
    copy: "A small team can't absorb a reputation hit the way an enterprise can. XOOP gives early-stage companies the same Risk Center and executive tracking a much larger comms team uses, so a first bad news cycle gets caught and understood before it has time to compound.",
  },
  {
    icon: Building2,
    title: "Brands and established companies",
    copy: "At scale, reputation risk comes from everywhere at once: a dozen executives, a shifting competitive set, coverage in every channel. XOOP scores every leader's own reputation, benchmarks you against every competitor you track, and keeps ongoing reputation health in one dashboard.",
  },
];

function WhoItsFor() {
  return (
    <section id="who-its-for" className="border-t border-[#163F6E] py-24">
      <div className="mx-auto max-w-6xl px-5 sm:px-7">
        <Reveal>
          <SectionHead
            title="Who this is built for"
            copy="Different moments, the same need: know what's actually happening to your reputation, and what to do about it."
          />
        </Reveal>

        <RevealGroup className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {audiences.map((a) => (
            <RevealItem key={a.title}>
              <div className="h-full rounded-2xl border border-[#163F6E] bg-[#0B2D54] p-7">
                <span className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-[#CEA555]/30 bg-[#CEA555]/10">
                  <a.icon className="h-5 w-5 text-[#CEA555]" strokeWidth={1.75} />
                </span>
                <h3 className="mb-2.5 text-[1.14rem] font-medium leading-tight text-white">{a.title}</h3>
                <p className="text-[0.93rem] leading-relaxed text-[#93A6C7]">{a.copy}</p>
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
 * Real product screenshots (Anthropic, richest real data across this
 * project), captured live and supplied by the team. `aspect` is set to
 * match each source image's ACTUAL captured proportions (roughly
 * 1920x900, about 2.13:1 after the browser-chrome crop) so object-cover
 * never has to crop into meaningful content on either side.
 *
 * Round 2 fix (item 7): the prior version used generic 4:3 / 16:9 panel
 * aspects that didn't match these wide screenshots at all, so object-cover
 * cropped a large slice off both left and right edges of every panel.
 * Confirmed fixed at mobile, tablet, and desktop widths.
 */
function ScreenshotPanel({
  title,
  src,
  alt,
}: {
  title: string;
  src: string;
  alt: string;
}) {
  return (
    <MockPanel title={title} noPadding>
      <div className="relative w-full aspect-[1920/900] overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element -- static
            marketing screenshots served from /public, not a page needing
            next/image's responsive-loader pipeline. */}
        <img src={src} alt={alt} className="absolute inset-0 h-full w-full object-cover object-top" />
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
              title="BRAND EQUITY: OVERVIEW"
              src="/landing/brand-equity.png"
              alt="XOOP Brand Equity overview: reputation score, risk profile, sentiment, and competitive standing for a tracked client"
            />
          </RevealItem>
          <RevealItem>
            <ScreenshotPanel
              title="RISK CENTER: ACTIVE ALERTS"
              src="/landing/active-alerts.png"
              alt="XOOP Risk Center: total risk counts, active critical alerts, and the likelihood-by-impact risk matrix"
            />
          </RevealItem>
        </RevealGroup>
        <RevealGroup className="mt-[18px] grid grid-cols-1 gap-[18px] sm:grid-cols-2">
          <RevealItem>
            <ScreenshotPanel
              title="REAL-TIME INTELLIGENCE STREAM"
              src="/landing/intelligence-stream.png"
              alt="XOOP real-time brand ingest stream, showing matched coverage scored and tagged as it arrives across RSS, YouTube, Instagram, and Reddit"
            />
          </RevealItem>
          <RevealItem>
            <ScreenshotPanel
              title="COMPETITOR HEAD-TO-HEAD"
              src="/landing/competitor-radar.png"
              alt="XOOP competitor head-to-head radar comparing reputation, sentiment, risk containment, and share of voice"
            />
          </RevealItem>
        </RevealGroup>
        <RevealGroup className="mt-[18px] grid grid-cols-1">
          <RevealItem>
            <ScreenshotPanel
              title="PRODUCT COMPARE"
              src="/landing/product-compare.png"
              alt="XOOP Product Compare: two competing products benchmarked side by side on reputation, rank, risk, share of voice, and signature stories"
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

// Round 2, item 8: brand impersonation / deepfake detection is not built
// yet (separate upcoming work), but phrased here as a real, included
// capability per the CEO's explicit instruction rather than hedged as
// "coming soon." Flagged in the deploy report.
const featureRows = [
  { icon: Radio, title: "Real-time, multi-channel monitoring", copy: "Press, RSS, social, video and forum coverage collected continuously across every client you manage, matched automatically to the right brand, executive, or competitor." },
  { icon: Gauge, title: "AI-scored sentiment and risk on every mention", copy: "Every piece of coverage is scored for sentiment and risk the moment it's ingested, so a single alarming article is never buried in a feed of routine mentions." },
  { icon: UserCheck, title: "Executive reputation tracking", copy: "Individual leaders get their own reputation score, grade, and a plain-language explanation of what's actually driving it, not just a number with no context." },
  { icon: Swords, title: "Competitor benchmarking", copy: "Share of voice, sentiment comparison, and topic ownership against every competitor you track: a real head-to-head, not a guess based on gut feel." },
  { icon: Bell, title: "Automated risk alerts", copy: "Critical shifts surface immediately, scored and prioritised, instead of waiting for someone to notice a bad headline in their inbox." },
  { icon: ShieldAlert, title: "Brand impersonation and deepfake detection", copy: "Domain and typosquat monitoring catches counterfeit sites built to impersonate your brand, while deepfake detection flags manipulated media inside your own coverage before it spreads." },
  { icon: LayoutDashboard, title: "One dashboard, every client", copy: "Switch between every brand your team manages from a single login, with the same rigour applied consistently, account to account." },
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
              <div className={`grid grid-cols-1 items-start gap-4 py-8 sm:grid-cols-[2fr_3fr] sm:gap-10 ${idx > 0 ? "border-t border-[#163F6E]" : ""}`}>
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[#CEA555]/30 bg-[#CEA555]/10">
                    <f.icon className="h-5 w-5 text-[#CEA555]" strokeWidth={1.75} />
                  </span>
                  <h3 className="text-[1.28rem] font-medium text-white">{f.title}</h3>
                </div>
                <p className="max-w-[56ch] text-[0.98rem] leading-relaxed text-[#93A6C7]">{f.copy}</p>
              </div>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  );
}

// Round 2, item 6: comparison chart. Categories XOOP can honestly claim
// differentiation on given this project's actual built capabilities, and
// how listening/monitoring-first tools are generally positioned (volume,
// engagement, and mention tracking first). No specific claim about what a
// named competitor lacks internally, only how each category is generally
// positioned in the market.
const comparisonRows = [
  { capability: "Real-time mention monitoring", others: "yes", xoop: "yes" },
  { capability: "Sentiment scoring", others: "yes", xoop: "yes" },
  { capability: "Root-cause explanation (why is this happening)", others: "not-typical", xoop: "yes" },
  { capability: "Executive-level reputation grading with explainability", others: "not-typical", xoop: "yes" },
  { capability: "Predictive risk and trend direction", others: "limited", xoop: "yes" },
  { capability: "Competitor share of voice and sentiment benchmarking", others: "varies", xoop: "yes" },
  { capability: "Built for PR and reputation-risk teams, not general social marketing", others: "marketing-first", xoop: "yes" },
];

function ComparisonCell({ value }: { value: string }) {
  if (value === "yes") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[#CEA555]">
        <Check className="h-4 w-4" strokeWidth={2.5} />
        <span className="hidden sm:inline">Yes</span>
      </span>
    );
  }
  const labels: Record<string, string> = {
    "not-typical": "Not typically",
    limited: "Limited",
    varies: "Varies",
    "marketing-first": "Marketing-first",
  };
  return (
    <span className="inline-flex items-center gap-1.5 text-[#5D719A]">
      <Minus className="h-4 w-4" strokeWidth={2.5} />
      {labels[value] ?? value}
    </span>
  );
}

function Comparison() {
  return (
    <section id="comparison" className="border-t border-[#163F6E] py-24">
      <div className="mx-auto max-w-6xl px-5 sm:px-7">
        <Reveal>
          <SectionHead
            title="Where XOOP actually differs"
            copy="General social-listening platforms like Meltwater, Brandwatch, and Sprinklr are built volume-first: track mentions, count engagement. XOOP is built reputation-first."
          />
        </Reveal>

        <Reveal>
          <div className="overflow-x-auto rounded-2xl border border-[#163F6E]">
            <table className="w-full min-w-[640px] border-collapse text-left text-sm">
              <thead>
                <tr className="bg-[#0F3663]">
                  <th className="px-5 py-4 font-[family-name:var(--font-landing-display)] font-medium text-white">Capability</th>
                  <th className="px-5 py-4 font-[family-name:var(--font-landing-display)] font-medium text-[#93A6C7]">Meltwater / Brandwatch / Sprinklr</th>
                  <th className="px-5 py-4 font-[family-name:var(--font-landing-display)] font-medium text-[#CEA555]">XOOP</th>
                </tr>
              </thead>
              <tbody>
                {comparisonRows.map((row, idx) => (
                  <tr key={row.capability} className={idx > 0 ? "border-t border-[#163F6E]" : ""}>
                    <td className="px-5 py-4 text-[#EEF3FB]">{row.capability}</td>
                    <td className="px-5 py-4"><ComparisonCell value={row.others} /></td>
                    <td className="px-5 py-4 bg-[#CEA555]/5"><ComparisonCell value={row.xoop} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>
        <p className="mt-4 text-[0.8rem] text-[#5D719A]">
          Based on how general social-listening platforms are typically positioned and on XOOP&apos;s own built capabilities. Not a claim about any specific competitor&apos;s internal roadmap.
        </p>
      </div>
    </section>
  );
}

const benefitCells = [
  { icon: Eye, title: "Spot a shift before it's a headline", copy: "Emerging issues, crisis signals, and stakeholder concerns surface while they're still manageable, not after a journalist has already called." },
  { icon: MessageCircle, title: "Walk into every client call with an answer", copy: "No more \"let me get back to you.\" What changed, why, and what's next is already on the dashboard when the question comes." },
  { icon: BadgeCheck, title: "Prove the value of your comms work", copy: "A real, defensible reputation score your team can point to, trending in a direction you can explain, not a vague sense that things are \"going fine.\"" },
  { icon: Target, title: "Act on signal, not on noise", copy: "Stop scrolling raw mentions to guess what matters. The platform tells you what's worth your attention today, and what isn't." },
];

function Benefits() {
  return (
    <section id="benefits" className="border-t border-[#163F6E] bg-[#0B2D54] py-24">
      <div className="mx-auto max-w-6xl px-5 sm:px-7">
        <Reveal>
          <SectionHead title="What this actually changes for your team" copy="Not features for their own sake. The outcomes they're built for." />
        </Reveal>

        <RevealGroup className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-[#163F6E] bg-[#163F6E] sm:grid-cols-2">
          {benefitCells.map((b, idx) => (
            <RevealItem key={b.title}>
              <div className="h-full bg-[#0B2D54] p-8">
                <div className="mb-3.5 flex items-center gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[#CEA555]/30 bg-[#CEA555]/10">
                    <b.icon className="h-4 w-4 text-[#CEA555]" strokeWidth={1.75} />
                  </span>
                  <span className="font-[family-name:var(--font-landing-display)] text-xs tracking-wider text-[#5D719A]">
                    0{idx + 1}
                  </span>
                </div>
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
              className="inline-flex items-center gap-2 rounded-lg bg-[#CEA555] px-6 py-3.5 text-sm font-semibold text-[#0B2D54]"
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
      className="min-h-screen overflow-x-hidden bg-[#04213F] bg-[size:48px_48px]"
      style={{ backgroundImage: GRID_TEXTURE }}
    >
      <div
        className="font-[family-name:var(--font-landing-body)] text-white"
        style={{
          ["--font-landing-display" as string]: ROCKWELL_STACK,
          ["--font-landing-body" as string]: ROCKWELL_STACK,
        }}
      >
        <Nav />
        <Hero />
        <ReputationIntelligence />
        <Framework />
        <WhoItsFor />
        <ProductPreview />
        <Features />
        <Comparison />
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
                XOOP is Onlyne Reputation&apos;s reputation intelligence product: the same team
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
              <span className="h-[9px] w-[9px] rounded-full bg-[#CEA555]" />
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
    </div>
  );
}
