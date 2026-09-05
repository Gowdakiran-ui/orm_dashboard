"use client";

import React, { useRef } from "react";
import { motion, useMotionTemplate, useMotionValue, useSpring } from "framer-motion";
import type { Theme } from "./ThemeProvider";
import { accentColors, glassTokens } from "./tokens";

/**
 * Full-effect glass wrapper (mouse-tracked spotlight border + a slow beam
 * riding the perimeter) reserved for a small number of genuinely prominent
 * elements per page -- see the redesign report for which ones. Everything
 * else gets the plain glassCard() base style, not this.
 */
export function HeroGlass({
  theme,
  children,
  className = "",
}: {
  theme: Theme;
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const rawX = useMotionValue(0);
  const rawY = useMotionValue(0);
  const springConfig = { stiffness: 300, damping: 30, mass: 0.5 };
  const x = useSpring(rawX, springConfig);
  const y = useSpring(rawY, springConfig);
  const { from, to } = accentColors(theme);
  const spotlight = useMotionTemplate`radial-gradient(360px circle at ${x}px ${y}px, ${from}55, transparent 60%)`;

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    rawX.set(e.clientX - rect.left);
    rawY.set(e.clientY - rect.top);
  }

  return (
    <div
      ref={ref}
      onMouseMove={handleMouseMove}
      className={`group relative overflow-hidden rounded-3xl ${glassTokens[theme].card} ${className}`}
    >
      <div className={glassTopSpecular} />

      {/* Mouse-tracked spotlight border glow */}
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-3xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{
          background: spotlight,
          padding: 1,
          WebkitMaskImage: "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)",
          maskImage: "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)",
          WebkitMaskComposite: "xor",
          maskComposite: "exclude",
        }}
      />

      {/* Slow comet riding the border -- a single subtle pass, not a spin loop */}
      <span
        aria-hidden
        className="pointer-events-none absolute left-0 top-0 h-5 w-16 animate-heroBeam rounded-full opacity-70"
        style={{
          offsetPath: "border-box",
          offsetRotate: "0deg",
          background: `linear-gradient(90deg, transparent, ${to}, ${from}, transparent)`,
          filter: "blur(5px)",
        }}
      />

      <div className="relative">{children}</div>

      <style jsx global>{`
        @keyframes heroBeam {
          from {
            offset-distance: 0%;
          }
          to {
            offset-distance: 100%;
          }
        }
        .animate-heroBeam {
          animation: heroBeam 6s linear infinite;
        }
        @media (prefers-reduced-motion: reduce) {
          .animate-heroBeam {
            animation: none !important;
          }
        }
      `}</style>
    </div>
  );
}

const glassTopSpecular =
  "pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/40 to-transparent";
