// SSRF-prevention check: rejects internal/private hosts, API endpoints,
// archives, and screenshot images before a URL is offered as an
// "Open Original Article" link.
export function isValidOriginalArticleUrl(url: string | null | undefined): boolean {
  if (!url) return false;
  try {
    const trimmed = url.trim();
    const parsed = new URL(trimmed);
    const hostname = parsed.hostname.toLowerCase();
    if (
      hostname === "localhost" ||
      hostname === "127.0.0.1" ||
      hostname.includes("internal") ||
      hostname.startsWith("192.168.") ||
      hostname.startsWith("10.")
    ) {
      return false;
    }
    const pathname = parsed.pathname.toLowerCase();
    if (pathname.includes("/api/") || pathname.endsWith("/api") || pathname.includes("/v1/") || pathname.includes("/v2/")) {
      return false;
    }
    const archiveExtensions = [".zip", ".tar", ".gz", ".tgz", ".rar", ".7z", ".bz2"];
    if (archiveExtensions.some(ext => pathname.endsWith(ext))) {
      return false;
    }
    const screenshotExtensions = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"];
    if (screenshotExtensions.some(ext => pathname.endsWith(ext)) || pathname.includes("screenshot") || pathname.includes("capture")) {
      return false;
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return false;
    }
    return true;
  } catch (e) {
    return false;
  }
}
