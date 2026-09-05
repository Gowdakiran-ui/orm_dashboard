"use client";

import React, { useRef } from "react";
import { motion, useMotionValue, useSpring } from "framer-motion";

/**
 * Wraps a button/link so it pulls gently toward the cursor within its own
 * bounds, then springs back to rest on leave — the "magnetic CTA" feel.
 * Pointer-based, so touch devices just get the plain element (no offset).
 */
export function MagneticButton({
  children,
  className = "",
  as: Component = motion.a,
  strength = 0.35,
  ...props
}: {
  children: React.ReactNode;
  className?: string;
  as?: React.ElementType;
  strength?: number;
  [key: string]: unknown;
}) {
  const ref = useRef<HTMLElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 250, damping: 18, mass: 0.4 });
  const springY = useSpring(y, { stiffness: 250, damping: 18, mass: 0.4 });

  function handleMouseMove(e: React.MouseEvent<HTMLElement>) {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const relX = e.clientX - (rect.left + rect.width / 2);
    const relY = e.clientY - (rect.top + rect.height / 2);
    x.set(relX * strength);
    y.set(relY * strength);
  }

  function handleMouseLeave() {
    x.set(0);
    y.set(0);
  }

  const MotionComponent = Component as typeof motion.a;

  return (
    <MotionComponent
      ref={ref as never}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{ x: springX, y: springY }}
      whileTap={{ scale: 0.96 }}
      className={className}
      {...props}
    >
      {children}
    </MotionComponent>
  );
}
