"use client";

import React from "react";
import { Sun, Moon } from "lucide-react";
import { useTheme } from "./ThemeProvider";

/** Compact sun/moon toggle -- sits with the sidebar's other top controls. */
export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";

  return (
    <button
      onClick={toggleTheme}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className={
        "flex flex-col items-center justify-center gap-0.5 min-w-[44px] min-h-[44px] transition-colors " +
        (isDark
          ? "text-zinc-500 hover:text-zinc-200"
          : "text-zinc-400 hover:text-zinc-700")
      }
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      <span className="text-xs leading-none">{isDark ? "Light" : "Dark"}</span>
    </button>
  );
}
