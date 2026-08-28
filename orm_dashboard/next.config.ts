import type { NextConfig } from "next";

// API_FORENSICS.md Section 9: no security headers existed anywhere. This
// dashboard is a client-rendered SPA-ish app (recharts + shadcn/tw-animate-css,
// no framer-motion in package.json despite the audit note) fetching from the
// backend at NEXT_PUBLIC_API_URL — connect-src must include that origin or
// every fetch silently fails.
//
// script-src/style-src need 'unsafe-inline': Next's app-router hydration
// payload (the __next_f inline <script> tags) and recharts' dynamically
// computed inline `style` attributes on SVG elements both need it. A
// stricter nonce-based CSP is possible but requires per-request nonce
// generation via middleware.ts, not the static headers() function used
// here -- noted as a follow-up, not implemented in this pass.
const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// React/Turbopack's dev-mode tooling (HMR, stack-trace reconstruction --
// see the "eval() is not supported" console error this fixes) calls eval(),
// which a script-src without 'unsafe-eval' silently blocks -- breaking
// hydration entirely in `next dev`, which is why the login button (and
// everything else) stopped responding. React itself guarantees it never
// calls eval() in a production build, so this is dev-only: a real
// onboarded client only ever hits the production build (`next build` /
// `next start`, or the Dockerfile), which gets the strict CSP unchanged.
const isDev = process.env.NODE_ENV !== "production";

const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' data:",
  `connect-src 'self' ${API_ORIGIN}`,
  "object-src 'none'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  /* config options here */
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
          { key: "Content-Security-Policy", value: CSP },
        ],
      },
    ];
  },
};

export default nextConfig;
