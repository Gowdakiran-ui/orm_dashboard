"""
Access guard for the Prometheus /metrics endpoint.

/metrics used to answer anyone who could reach the API, including through the public reverse proxy (api.xoop...). Nothing scrapes it
today (no Prometheus process or scrape config on the droplet), so it is locked down without breaking monitoring:

  * METRICS_TOKEN set   -> a request needs `Authorization: Bearer <token>` (constant-time comparison), from anywhere.
  * METRICS_TOKEN unset -> only requests from the internal network are answered: the client address is loopback or private
                           (the docker network, localhost) AND the request carries none of the headers a reverse proxy adds
                           (X-Forwarded-For, X-Forwarded-Host, X-Forwarded-Proto, X-Real-IP, Forwarded). The proxy on this host reaches the API
                           from a private docker address too, so the address alone cannot tell it apart; the headers can.
A future Prometheus container on the compose network keeps working untouched (no proxy headers, private address); an external scraper
needs a token. Everything else is untouched: the guard looks at the path /metrics only.
"""
import hmac
import ipaddress
import os
from typing import Iterable, Optional, Tuple

_PROXY_HEADERS = (b"x-forwarded-for", b"x-forwarded-host", b"x-forwarded-proto", b"x-real-ip", b"forwarded")


# Spelled out on purpose: ipaddress.is_private also covers documentation and other reserved ranges that are not "our network".
_INTERNAL_NETS = tuple(ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7", "fe80::/10"))


def _is_internal(host: Optional[str]) -> bool:
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in net for net in _INTERNAL_NETS if net.version == ip.version)


def metrics_decision(headers: Iterable[Tuple[bytes, bytes]], client_host: Optional[str], token: Optional[str]) -> Tuple[bool, int]:
    """(allowed, status to answer with when not allowed). `headers` as in an ASGI scope (lower-case names)."""
    hdrs = {k.lower(): v for k, v in headers}
    token = (token or "").strip()
    if token:
        auth = hdrs.get(b"authorization", b"").decode("latin-1")
        scheme, _, given = auth.partition(" ")
        if scheme.lower() == "bearer" and given and hmac.compare_digest(given.strip().encode(), token.encode()):
            return True, 200
        return False, 401
    if any(h in hdrs for h in _PROXY_HEADERS) or not _is_internal(client_host):
        return False, 403
    return True, 200


class MetricsGuardMiddleware:
    """Pure ASGI middleware: answers /metrics only when metrics_decision allows it."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/metrics":
            client = scope.get("client")
            allowed, status = metrics_decision(scope.get("headers") or [], client[0] if client else None, os.environ.get("METRICS_TOKEN"))
            if not allowed:
                body = b"Unauthorized" if status == 401 else b"Forbidden"
                headers = [(b"content-type", b"text/plain; charset=utf-8"), (b"content-length", str(len(body)).encode())]
                if status == 401:
                    headers.append((b"www-authenticate", b"Bearer"))
                await send({"type": "http.response.start", "status": status, "headers": headers})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
