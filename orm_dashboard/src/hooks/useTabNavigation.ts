"use client";

import { useCallback } from "react";
import { useRouter, usePathname, useSearchParams, type ReadonlyURLSearchParams } from "next/navigation";

const DEFAULT_TAB = "reputation";
const DEFAULT_SUBTAB = "overview";

/**
 * Single source of truth for dashboard tab state, backed by the URL
 * (?tab=risk&subtab=... plus whatever filter params a caller adds) instead
 * of local useState -- so tab switches are real history entries (browser
 * Back/Forward works) and a tab + filter combination is a shareable link.
 *
 * Any client component under the dashboard page can call this directly
 * (no prop drilling required) since it just reads/writes the URL that's
 * already shared across the whole tree.
 */
export function useTabNavigation() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const activeTab = searchParams.get("tab") || DEFAULT_TAB;
  const analyticsSubTab = searchParams.get("subtab") || DEFAULT_SUBTAB;

  // The one shared navigate-and-filter primitive (Part B): switches to
  // `tab` and replaces the query string with exactly the given params --
  // any filter param not passed here is dropped, so a fresh drill-through
  // never drags a stale filter from wherever the user came from. Always
  // router.push (never replace) so every tab/filter change is a real,
  // back-navigable history entry.
  const navigateTo = useCallback(
    (tab: string, params: Record<string, string | undefined> = {}) => {
      const next = new URLSearchParams();
      next.set("tab", tab);
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== "") next.set(key, value);
      }
      router.push(`${pathname}?${next.toString()}`);
    },
    [router, pathname]
  );

  const setActiveTab = useCallback((tab: string) => navigateTo(tab), [navigateTo]);
  const setAnalyticsSubTab = useCallback(
    (subtab: string) => navigateTo("analytics", { subtab }),
    [navigateTo]
  );

  return {
    activeTab,
    analyticsSubTab,
    setActiveTab,
    setAnalyticsSubTab,
    navigateTo,
    searchParams: searchParams as ReadonlyURLSearchParams,
  };
}
