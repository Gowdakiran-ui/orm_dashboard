"use client";

/**
 * A short comet of light that travels the perimeter of its parent (parent
 * needs `position:relative` + `overflow-hidden`). Uses `offset-path:
 * border-box` so it literally rides the element's own border, not a
 * hand-measured path.
 */
export function BorderBeam({ duration = 6 }: { duration?: number }) {
  return (
    <span
      aria-hidden
      className="pointer-events-none absolute left-0 top-0 h-6 w-20 animate-borderBeam rounded-full"
      style={{
        offsetPath: "border-box",
        offsetRotate: "0deg",
        background: "linear-gradient(90deg, transparent, #FFB703, #FF5E00, transparent)",
        filter: "blur(6px)",
        animationDuration: `${duration}s`,
      }}
    />
  );
}
