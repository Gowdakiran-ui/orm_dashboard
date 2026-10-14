"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "xoop-dashboard-theme";

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

/**
 * Dashboard-only theme state (Crystalline Glass / Smoked Obsidian Glass).
 * Persisted to localStorage, defaults to dark to match the app's existing
 * look. Purely presentational -- never read by any data-fetching hook.
 */
export function ThemeProvider({ children, forcedTheme }: { children: React.ReactNode; forcedTheme?: Theme }) {
  const [theme, setTheme] = useState<Theme>("dark");
  const [hydrated, setHydrated] = useState(false);

  // forcedTheme (used only by the Export Report chart stage, which must always render light):
  // the provider shows that theme and never reads, writes or toggles the user's saved preference.
  // Left undefined (every existing caller), nothing below changes.
  useEffect(() => {
    if (forcedTheme) return;
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "light" || stored === "dark") setTheme(stored);
    } catch {
      // localStorage unavailable (private mode, etc.) -- keep the dark default.
    }
    setHydrated(true);
  }, [forcedTheme]);

  useEffect(() => {
    if (forcedTheme || !hydrated) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // ignore write failures
    }
  }, [theme, hydrated, forcedTheme]);

  function toggleTheme() {
    if (forcedTheme) return;
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }

  return (
    <ThemeContext.Provider value={{ theme: forcedTheme ?? theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
