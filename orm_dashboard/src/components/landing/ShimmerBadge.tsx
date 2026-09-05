"use client";

import React from "react";

/** Pill badge with a metallic light sweep passing through the text. */
export function ShimmerBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-zinc-800 bg-zinc-900 px-3 py-1 font-[family-name:var(--font-landing-mono)] text-[11px] font-medium uppercase tracking-wider">
      <span
        className="animate-shimmerText bg-[length:200%_100%] bg-clip-text text-transparent"
        style={{
          backgroundImage:
            "linear-gradient(110deg, #9CA1AC 40%, #FFFFFF 50%, #9CA1AC 60%)",
        }}
      >
        {children}
      </span>
    </span>
  );
}
