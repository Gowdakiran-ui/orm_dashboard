"""
counterfeit_detection.py — API clients for the Counterfeit Detection page's
two on-demand tools (not a pipeline stage, see PART task brief):

  * Reality Defender  — deepfake/manipulation scan for an uploaded image.
    Contract confirmed against the official Python SDK source
    (github.com/Reality-Defender/realitydefender-sdk-python,
    src/realitydefender/{core/constants.py,detection/upload.py}) and the
    public API reference (docs.realitydefender.com) on 2026-09-23. Free
    tier: 50 scans/month, image + audio only.

  * WhoisFreaks Typosquatting API + Live WHOIS API — finds lookalike
    domains for a brand keyword, then looks up registrar/create date per
    candidate. Both endpoints confirmed live against whoisfreaks.com's own
    rendered docs (the request curl examples) on 2026-09-23. Typosquat
    free tier: 500 credits total (not monthly) -- callers must not loop
    pages or re-scan casually.

  * Bolster.ai (CheckPhish) Scan API — live/malicious status for a
    candidate domain. Contract NOT independently confirmed against
    Bolster's own docs -- those pages sit behind a Cloudflare bot check
    this session correctly did not attempt to bypass. Based on two
    independent search-result snippets describing
    developers.checkphish.ai/api/neo/scan/ (submit) and
    .../neo/scan/status (poll), which agreed with each other. Treat this
    one contract as the most likely to need a field-name fix after the
    first real live call -- errors are surfaced with the raw response
    body (not swallowed) specifically so that's easy to diagnose. Free
    tier: 25 scans/day.
"""
import time
from typing import Any, Dict, List, Optional

import requests
import structlog

from app.core.config import settings

logger = structlog.get_logger()

# Cap on how many typosquat candidates get a live Bolster scan per search.
# WhoisFreaks can return up to 100 candidates/page; Bolster's free tier is
# 25 scans/day total for the whole platform. Scanning every candidate on
# one search could exhaust the entire daily quota in a single click, so
# this call only live-checks the top N (by most-recently-seen) rather than
# looping every result. Judgment call, not a documented limit — flagged
# back to the user, not guessed silently.
MAX_DOMAINS_TO_LIVE_CHECK = 10

REALITY_DEFENDER_BASE = "https://api.prd.realitydefender.xyz"
WHOISFREAKS_BASE = "https://api.whoisfreaks.com"
BOLSTER_BASE = "https://developers.checkphish.ai/api"

_RD_POLL_INTERVAL_S = 2
_RD_MAX_ATTEMPTS = 30  # matches the SDK's own default (60s total)


class CounterfeitDetectionUnavailable(Exception):
    """Raised when a tool's API key isn't configured."""


class CounterfeitDetectionError(Exception):
    """Raised on a call that reached the provider but failed (bad input,
    quota exhausted, provider error) — message is safe to show the user."""


# ---------------------------------------------------------------------
# Reality Defender — deepfake image scan
# ---------------------------------------------------------------------

def scan_image_for_deepfake(image_bytes: bytes, filename: str, content_type: str) -> Dict[str, Any]:
    """
    Uploads `image_bytes` to Reality Defender and polls for a verdict.

    Returns {"verdict": "AUTHENTIC"|"FAKE"|"SUSPICIOUS"|"NOT_APPLICABLE"|"UNABLE_TO_EVALUATE",
             "confidence_score": float 0-100, "request_id": str}

    Raises CounterfeitDetectionUnavailable if no API key is configured,
    CounterfeitDetectionError on a quota/auth/provider failure or timeout.
    """
    if not settings.REALITY_DEFENDER_API_KEY:
        raise CounterfeitDetectionUnavailable("Reality Defender API key not configured")

    headers = {"X-API-KEY": settings.REALITY_DEFENDER_API_KEY}

    try:
        presign_resp = requests.post(
            f"{REALITY_DEFENDER_BASE}/api/files/aws-presigned",
            headers=headers,
            json={"fileName": filename},
            timeout=30,
        )
    except requests.RequestException as e:
        raise CounterfeitDetectionError(f"Could not reach Reality Defender: {e}") from e

    if presign_resp.status_code == 429:
        raise CounterfeitDetectionError("Reality Defender free-tier quota exhausted (50 scans/month)")
    if presign_resp.status_code == 401:
        raise CounterfeitDetectionError("Reality Defender rejected the API key")
    if presign_resp.status_code >= 400:
        raise CounterfeitDetectionError(f"Reality Defender upload request failed: HTTP {presign_resp.status_code}: {presign_resp.text[:300]}")

    presign_data = presign_resp.json()
    request_id = presign_data.get("requestId")
    signed_url = (presign_data.get("response") or {}).get("signedUrl")
    if not request_id or not signed_url:
        raise CounterfeitDetectionError("Reality Defender returned an unexpected upload response (missing requestId/signedUrl)")

    try:
        put_resp = requests.put(signed_url, data=image_bytes, headers={"Content-Type": content_type}, timeout=60)
    except requests.RequestException as e:
        raise CounterfeitDetectionError(f"Uploading image to Reality Defender failed: {e}") from e
    if put_resp.status_code >= 400:
        raise CounterfeitDetectionError(f"Uploading image to Reality Defender failed: HTTP {put_resp.status_code}")

    for attempt in range(_RD_MAX_ATTEMPTS):
        time.sleep(_RD_POLL_INTERVAL_S)
        try:
            result_resp = requests.get(
                f"{REALITY_DEFENDER_BASE}/api/media/users/{request_id}",
                headers=headers,
                timeout=30,
            )
        except requests.RequestException as e:
            logger.warning("reality_defender_poll_failed", attempt=attempt, error=str(e))
            continue

        if result_resp.status_code >= 400:
            continue

        result_data = result_resp.json()
        results_summary = result_data.get("resultsSummary")
        if results_summary and results_summary.get("status"):
            metadata = results_summary.get("metadata") or {}
            return {
                "verdict": results_summary["status"],
                "confidence_score": metadata.get("finalScore"),
                "request_id": request_id,
            }

    raise CounterfeitDetectionError("Reality Defender did not return a result within 60 seconds")


# ---------------------------------------------------------------------
# WhoisFreaks — typosquat discovery + per-candidate WHOIS lookup
# ---------------------------------------------------------------------

def find_typosquat_candidates(keyword: str) -> List[Dict[str, Any]]:
    """
    Returns up to one page (100) of candidate lookalike domains for
    `keyword`: [{"domain_name", "create_date", "expiry_date", "last_seen", "is_dropped"}, ...]

    Only fetches page 1 — deliberately not looping pageToken, since each
    page costs WhoisFreaks credits against the 500-credit free tier and
    100 candidates is already far more than the Bolster live-check step
    (capped at MAX_DOMAINS_TO_LIVE_CHECK) will use.
    """
    if not settings.WHOISFREAKS_API_KEY:
        raise CounterfeitDetectionUnavailable("WhoisFreaks API key not configured")

    try:
        resp = requests.get(
            f"{WHOISFREAKS_BASE}/v3.0/domain/typos",
            params={"apiKey": settings.WHOISFREAKS_API_KEY, "keyword": keyword},
            timeout=30,
        )
    except requests.RequestException as e:
        raise CounterfeitDetectionError(f"Could not reach WhoisFreaks: {e}") from e

    if resp.status_code == 402 or resp.status_code == 429:
        raise CounterfeitDetectionError("WhoisFreaks free-tier credits exhausted (500 credits total)")
    if resp.status_code == 401:
        raise CounterfeitDetectionError("WhoisFreaks rejected the API key")
    if resp.status_code >= 400:
        raise CounterfeitDetectionError(f"WhoisFreaks typosquat lookup failed: HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    if not data.get("status"):
        raise CounterfeitDetectionError("WhoisFreaks returned an unsuccessful response for this keyword")

    return [
        {
            "domain_name": d.get("domainName"),
            "create_date": d.get("createDate"),
            "expiry_date": d.get("expiryDate"),
            "last_seen": d.get("lastSeen"),
            "is_dropped": d.get("isDropped"),
        }
        for d in (data.get("domains") or [])
    ]


def lookup_registrar(domain_name: str) -> Optional[Dict[str, Any]]:
    """
    Live WHOIS lookup for one domain — registrar name + create date.
    Returns None (not an exception) on failure: this enriches a candidate
    row that should still render even if the registrar lookup itself fails,
    same "degrade, don't block" convention as document_service.py's S3
    upload path.
    """
    if not settings.WHOISFREAKS_API_KEY:
        return None
    try:
        resp = requests.get(
            f"{WHOISFREAKS_BASE}/v2.0/whois/live",
            params={"apiKey": settings.WHOISFREAKS_API_KEY, "domainName": domain_name, "format": "json"},
            timeout=20,
        )
        if resp.status_code >= 400:
            return None
        data = resp.json()
        if not data.get("status"):
            return None
        registrar = (data.get("domain_registrar") or {}).get("registrar_name")
        return {"registrar": registrar, "create_date": data.get("create_date")}
    except requests.RequestException as e:
        logger.warning("whoisfreaks_registrar_lookup_failed", domain=domain_name, error=str(e))
        return None


# ---------------------------------------------------------------------
# Bolster.ai (CheckPhish) — live/malicious status for a candidate domain
# ---------------------------------------------------------------------

def check_domain_live_status(domain_name: str) -> Dict[str, Any]:
    """
    Submits `domain_name` for a quick scan and polls for disposition.

    Returns {"live": bool, "malicious": bool, "disposition": str}.

    See module docstring: this contract is the least independently
    verified of the three (Bolster's own docs sit behind a Cloudflare
    challenge). If field names below turn out wrong on the first live
    call, the raw response body is included in the raised error so it's
    fast to fix.
    """
    if not settings.BOLSTER_API_KEY:
        raise CounterfeitDetectionUnavailable("Bolster API key not configured")

    url_to_scan = domain_name if domain_name.startswith(("http://", "https://")) else f"http://{domain_name}"

    try:
        submit_resp = requests.post(
            f"{BOLSTER_BASE}/neo/scan/",
            json={"apiKey": settings.BOLSTER_API_KEY, "urlInfo": {"url": url_to_scan}, "scanType": "quick"},
            timeout=30,
        )
    except requests.RequestException as e:
        raise CounterfeitDetectionError(f"Could not reach Bolster: {e}") from e

    if submit_resp.status_code == 429:
        raise CounterfeitDetectionError("Bolster free-tier quota exhausted (25 scans/day)")
    if submit_resp.status_code == 401:
        raise CounterfeitDetectionError("Bolster rejected the API key")
    if submit_resp.status_code >= 400:
        raise CounterfeitDetectionError(f"Bolster scan submission failed: HTTP {submit_resp.status_code}: {submit_resp.text[:300]}")

    job_id = submit_resp.json().get("jobID")
    if not job_id:
        raise CounterfeitDetectionError(f"Bolster returned an unexpected submit response (no jobID): {submit_resp.text[:300]}")

    for attempt in range(15):  # quick scans are typically fast; ~30s ceiling
        time.sleep(2)
        try:
            status_resp = requests.post(
                f"{BOLSTER_BASE}/neo/scan/status",
                json={"apiKey": settings.BOLSTER_API_KEY, "jobID": job_id},
                timeout=20,
            )
        except requests.RequestException as e:
            logger.warning("bolster_poll_failed", attempt=attempt, error=str(e))
            continue

        if status_resp.status_code >= 400:
            continue

        status_data = status_resp.json()
        disposition = status_data.get("disposition")
        if disposition and disposition != "PENDING":
            malicious = disposition.lower() in ("phish", "malicious", "suspicious")
            return {"live": True, "malicious": malicious, "disposition": disposition}

    raise CounterfeitDetectionError("Bolster did not return a result within 30 seconds")
