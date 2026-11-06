"use client";

import React from "react";
import { Sun, Moon, Monitor } from "lucide-react";
import { useTheme, type ThemePreference } from "./ThemeProvider";

const OPTIONS: { value: ThemePreference; label: string; Icon: typeof Sun }[] = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "System", Icon: Monitor },
];

/** Light / Dark / System selector -- sits with the sidebar's other top controls. */
export function ThemeToggle() {
  const { preference, setPreference } = useTheme();

  return (
    <div role="radiogroup" aria-label="Colour theme" className="flex items-center gap-1">
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = preference === value;
        return (
          <button
            key={value}
            role="radio"
            aria-checked={active}
            aria-label={`${label} theme`}
            title={`${label} theme`}
            onClick={() => setPreference(value)}
            className={
              "flex flex-col items-center justify-center gap-0.5 min-w-[44px] min-h-[44px] rounded-md border transition-colors " +
              (active
                ? "border-[var(--brand)] text-[var(--brand)] bg-[var(--brand)]/10"
                : "border-transparent text-[var(--fg-muted)] hover:text-[var(--fg)]")
            }
          >
            <Icon className="h-4 w-4" />
            <span className="text-xs leading-none">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
