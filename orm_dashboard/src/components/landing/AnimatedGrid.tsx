"use client";

/**
 * Slow-panning grid backdrop for the hero, faded out toward the edges via a
 * radial mask so it reads as atmosphere rather than a tiled texture.
 */
export function AnimatedGrid() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 overflow-hidden [mask-image:radial-gradient(ellipse_60%_60%_at_50%_0%,black_10%,transparent_75%)]"
    >
      <div className="absolute inset-0 animate-gridPan bg-[linear-gradient(to_right,#27272a_1px,transparent_1px),linear-gradient(to_bottom,#27272a_1px,transparent_1px)] bg-[size:64px_64px] opacity-40" />
    </div>
  );
}
