import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ORM Intelligence Platform",
  description: "Enterprise Reputation Intelligence Command Center",
};

export const viewport: Viewport = {
  colorScheme: "light dark",
};

// Runs before first paint (blocking inline script in <head>): resolves the
// saved Light / Dark / System choice and sets data-theme, color-scheme's
// source, and meta theme-color so there is no flash on reload. Dashboard
// routes only -- the landing and login pages are dark-only and carry no
// data-theme. Keep the storage key and colours in sync with
// components/theme/ThemeProvider.tsx.
const PRE_PAINT = `(function(){try{
var p=location.pathname;if(p.indexOf("/dashboard")!==0)return;
var v=localStorage.getItem("xoop-dashboard-theme");
var t=(v==="light"||v==="dark")?v:(window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");
document.documentElement.setAttribute("data-theme",t);
var m=document.querySelector('meta[name="theme-color"]');
if(!m){m=document.createElement("meta");m.name="theme-color";document.head.appendChild(m);}
m.content=t==="dark"?"#0F1419":"#F5F7FA";
}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: PRE_PAINT }} />
      </head>
      <body className="min-h-full flex flex-col font-sans">{children}</body>
    </html>
  );
}
