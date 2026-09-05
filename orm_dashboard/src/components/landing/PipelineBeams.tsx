"use client";

import React, { useRef } from "react";
import { Newspaper, MessageSquare, Users, Star, Sparkles, ShieldAlert } from "lucide-react";
import { AnimatedBeam } from "./AnimatedBeam";
import { useMediaQuery } from "./useMediaQuery";

function BeamNode({
  nodeRef,
  icon: Icon,
  label,
  accent = false,
}: {
  nodeRef: React.RefObject<HTMLDivElement | null>;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  accent?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 sm:flex-col sm:gap-2">
      <div
        ref={nodeRef}
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border sm:h-12 sm:w-12 ${
          accent ? "border-[#FF5E00]/50 bg-[#FF5E00]/10" : "border-zinc-800 bg-zinc-900"
        }`}
      >
        <Icon className={`h-5 w-5 ${accent ? "text-[#FF5E00]" : "text-zinc-400"}`} />
      </div>
      <span className="font-[family-name:var(--font-landing-mono)] text-[10px] uppercase tracking-wider text-zinc-500">
        {label}
      </span>
    </div>
  );
}

/**
 * Desktop/tablet: sources fan into the XOOP node, which feeds one beam out
 * to the score. Below sm, that horizontal fan has nowhere to go, so it
 * collapses into a single vertical chain instead of shrinking in place.
 */
export function PipelineBeams() {
  const isRow = useMediaQuery("(min-width: 640px)");
  const containerRef = useRef<HTMLDivElement>(null);
  const newsRef = useRef<HTMLDivElement>(null);
  const socialRef = useRef<HTMLDivElement>(null);
  const forumsRef = useRef<HTMLDivElement>(null);
  const reviewsRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<HTMLDivElement>(null);
  const scoreRef = useRef<HTMLDivElement>(null);

  if (!isRow) {
    return (
      <div ref={containerRef} className="relative mx-auto flex max-w-xs flex-col gap-8 py-8">
        <BeamNode nodeRef={newsRef} icon={Newspaper} label="News" />
        <BeamNode nodeRef={socialRef} icon={MessageSquare} label="Social" />
        <BeamNode nodeRef={forumsRef} icon={Users} label="Forums" />
        <BeamNode nodeRef={reviewsRef} icon={Star} label="Reviews" />
        <BeamNode nodeRef={engineRef} icon={Sparkles} label="XOOP" accent />
        <BeamNode nodeRef={scoreRef} icon={ShieldAlert} label="Score" accent />
        <AnimatedBeam containerRef={containerRef} fromRef={newsRef} toRef={socialRef} delay={0} />
        <AnimatedBeam containerRef={containerRef} fromRef={socialRef} toRef={forumsRef} delay={0.4} />
        <AnimatedBeam containerRef={containerRef} fromRef={forumsRef} toRef={reviewsRef} delay={0.8} />
        <AnimatedBeam containerRef={containerRef} fromRef={reviewsRef} toRef={engineRef} delay={1.2} />
        <AnimatedBeam containerRef={containerRef} fromRef={engineRef} toRef={scoreRef} delay={1.6} />
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="relative mx-auto grid max-w-3xl grid-cols-3 items-center gap-4 py-10"
    >
      <div className="col-span-1 flex flex-col gap-8 sm:gap-10">
        <BeamNode nodeRef={newsRef} icon={Newspaper} label="News" />
        <BeamNode nodeRef={socialRef} icon={MessageSquare} label="Social" />
        <BeamNode nodeRef={forumsRef} icon={Users} label="Forums" />
        <BeamNode nodeRef={reviewsRef} icon={Star} label="Reviews" />
      </div>

      <div className="col-span-1 flex justify-center">
        <BeamNode nodeRef={engineRef} icon={Sparkles} label="XOOP" accent />
      </div>

      <div className="col-span-1 flex justify-center">
        <BeamNode nodeRef={scoreRef} icon={ShieldAlert} label="Score" accent />
      </div>

      <AnimatedBeam containerRef={containerRef} fromRef={newsRef} toRef={engineRef} curvature={-20} delay={0} />
      <AnimatedBeam containerRef={containerRef} fromRef={socialRef} toRef={engineRef} curvature={-6} delay={0.4} />
      <AnimatedBeam containerRef={containerRef} fromRef={forumsRef} toRef={engineRef} curvature={6} delay={0.8} />
      <AnimatedBeam containerRef={containerRef} fromRef={reviewsRef} toRef={engineRef} curvature={20} delay={1.2} />
      <AnimatedBeam containerRef={containerRef} fromRef={engineRef} toRef={scoreRef} delay={1.6} />
    </div>
  );
}
