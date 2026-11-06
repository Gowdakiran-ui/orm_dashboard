"use client";

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

/** The resolved theme components render with. */
export type Theme = "light" | "dark";
/** What the user chose. "system" follows the OS setting. */
export type ThemePreference = Theme | "system";

export const STORAGE_KEY = "xoop-dashboard-theme";
export const META_COLORS: Record<Theme, string> = { light: "#F5F7FA", dark: "#0F1419" };

interface ThemeContextValue {
  theme: Theme;
  preference: ThemePreference;
  setPreference: (p: ThemePreference) => void;
  /** Kept for existing callers: flips the resolved theme. */
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function systemTheme(): Theme {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "dark";
  }
}

function readPreference(): ThemePreference {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    // storage unavailable -- fall through to the default
  }
  return "system";
}

/** Writes data-theme (drives the CSS tokens and color-scheme) and meta theme-color. */
function applyToDocument(theme: Theme) {
  const el = document.documentElement;
  el.setAttribute("data-theme", theme);
  let meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement("meta");
    meta.setAttribute("name", "theme-color");
    document.head.appendChild(meta);
  }
  meta.setAttribute("content", META_COLORS[theme]);
}

/**
 * Dashboard-only theme state. Preference is Light / Dark / System (default
 * System), persisted to localStorage. layout.tsx's inline script applies the
 * same choice before first paint; this provider keeps it in sync afterwards.
 * Purely presentational -- never read by any data-fetching hook.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Server render and first client render agree on "dark"; the effect below
  // corrects it immediately (the page background is already right from CSS).
  const [preference, setPreferenceState] = useState<ThemePreference>("system");
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const pref = readPreference();
    setPreferenceState(pref);
    setTheme(pref === "system" ? systemTheme() : pref);
  }, []);

  useEffect(() => {
    if (preference !== "system" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setTheme(mq.matches ? "dark" : "light");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [preference]);

  useEffect(() => {
    applyToDocument(theme);
  }, [theme]);

  // Landing and login pages are dark-only: drop the attribute on leaving the
  // dashboard. Re-applies on mount too, so StrictMode's mount/unmount/mount
  // in development doesn't leave the attribute removed.
  const themeRef = useRef<Theme>(theme);
  themeRef.current = theme;
  useEffect(() => {
    applyToDocument(themeRef.current);
    return () => document.documentElement.removeAttribute("data-theme");
  }, []);

  const setPreference = useCallback((p: ThemePreference) => {
    setPreferenceState(p);
    setTheme(p === "system" ? systemTheme() : p);
    try {
      window.localStorage.setItem(STORAGE_KEY, p);
    } catch {
      // ignore write failures
    }
  }, []);

  const toggleTheme = useCallback(() => setPreference(theme === "dark" ? "light" : "dark"), [theme, setPreference]);

  return (
    <ThemeContext.Provider value={{ theme, preference, setPreference, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
