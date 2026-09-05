"use client";

import React, { useEffect, useId, useRef, useState } from "react";
import { motion } from "framer-motion";

/**
 * Glowing line from `fromRef` to `toRef`, both measured relative to
 * `containerRef`. A gradient-filled stroke travels the path on a loop to
 * read as data flowing between the two nodes, not a static connector.
 */
export function AnimatedBeam({
  containerRef,
  fromRef,
  toRef,
  curvature = 0,
  delay = 0,
  reverse = false,
}: {
  containerRef: React.RefObject<HTMLElement | null>;
  fromRef: React.RefObject<HTMLElement | null>;
  toRef: React.RefObject<HTMLElement | null>;
  curvature?: number;
  delay?: number;
  reverse?: boolean;
}) {
  const id = useId().replace(/:/g, "");
  const [path, setPath] = useState("");
  const [box, setBox] = useState({ width: 0, height: 0 });

  useEffect(() => {
    function update() {
      const container = containerRef.current;
      const from = fromRef.current;
      const to = toRef.current;
      if (!container || !from || !to) return;

      const containerRect = container.getBoundingClientRect();
      const fromRect = from.getBoundingClientRect();
      const toRect = to.getBoundingClientRect();

      const startX = fromRect.left - containerRect.left + fromRect.width / 2;
      const startY = fromRect.top - containerRect.top + fromRect.height / 2;
      const endX = toRect.left - containerRect.left + toRect.width / 2;
      const endY = toRect.top - containerRect.top + toRect.height / 2;

      const midX = (startX + endX) / 2;
      const midY = (startY + endY) / 2 - curvature;

      setBox({ width: containerRect.width, height: containerRect.height });
      setPath(`M ${startX},${startY} Q ${midX},${midY} ${endX},${endY}`);
    }

    update();
    const ro = new ResizeObserver(update);
    if (containerRef.current) ro.observe(containerRef.current);
    window.addEventListener("resize", update);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [containerRef, fromRef, toRef, curvature]);

  if (!path) return null;

  return (
    <svg
      className="pointer-events-none absolute left-0 top-0 z-0"
      width={box.width}
      height={box.height}
      viewBox={`0 0 ${box.width} ${box.height}`}
    >
      <path d={path} stroke="#27272a" strokeWidth="1" fill="none" />
      <path d={path} stroke={`url(#beam-grad-${id})`} strokeWidth="2" fill="none" strokeLinecap="round" />
      <defs>
        <motion.linearGradient
          id={`beam-grad-${id}`}
          gradientUnits="userSpaceOnUse"
          initial={{
            x1: reverse ? "90%" : "0%",
            x2: reverse ? "100%" : "10%",
            y1: "0%",
            y2: "0%",
          }}
          animate={{
            x1: reverse ? ["90%", "-10%"] : ["0%", "100%"],
            x2: reverse ? ["100%", "0%"] : ["10%", "110%"],
          }}
          transition={{
            duration: 3.5,
            repeat: Infinity,
            repeatDelay: 0.5,
            delay,
            ease: [0.16, 1, 0.3, 1],
          }}
        >
          <stop stopColor="#FF5E00" stopOpacity="0" />
          <stop stopColor="#FF5E00" />
          <stop offset="1" stopColor="#FFB703" stopOpacity="0" />
        </motion.linearGradient>
      </defs>
    </svg>
  );
}
