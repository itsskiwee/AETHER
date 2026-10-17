"""Outbound network policy (Parameter_2 SEC-IN-011). Owned by the integrator lane (L1).

Every adapter that fetches over the network must pass its URL through ``require_allowed_url``
before connecting, and ``assert_public_address`` after DNS resolution, then use
``TIMEOUTS_S``. Only the packages listed in ``NETWORK_MODULE_PREFIXES`` may import HTTP or socket
libraries at all; ``tests/unit/test_security_baseline.py`` enforces that.

Adding a host is a reviewed change: add it here with the dataset it serves, and record the
provider's terms in DATA_LICENSES.md in the same PR.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_HOSTS: dict[str, str] = {
    "urs.earthdata.nasa.gov": "NASA Earthdata login (EMIT V002, ING-02)",
    "cmr.earthdata.nasa.gov": "NASA CMR granule search (EMIT V002, ING-02)",
    "data.lpdaac.earthdatacloud.nasa.gov": "LP DAAC EMIT V002 file downloads (ING-02)",
    "api.carbonmapper.org": "Carbon Mapper Data Platform API (ING-06, P1)",
    "celestrak.org": "CelesTrak GP orbital elements (archive mode, P1)",
    "cds.climate.copernicus.eu": "Copernicus CDS ERA5 reanalysis (SIM-02)",
    "ssd.jpl.nasa.gov": "JPL DE421 planetary ephemeris, one-time pinned fetch (ORB-07)",
}

# (connect, read) seconds, SEC-IN-011.
TIMEOUTS_S: tuple[float, float] = (10.0, 60.0)

# Package path prefixes (relative to the repository root) allowed to import network libraries.
NETWORK_MODULE_PREFIXES: tuple[str, ...] = (
    "backend/aether/netpolicy.py",
    "backend/aether/ingestion/",
    "backend/aether/weather/era5",
    "backend/aether/orbit/ephemeris",
    "scripts/",
)


class DisallowedURLError(ValueError):
    """Raised when a URL or resolved address violates the outbound policy."""


def require_allowed_url(url: str) -> str:
    """Return ``url`` unchanged if it may be fetched, else raise DisallowedURLError.

    Rules: https only; no credentials in the URL; default port only; host must be an exact
    allowlist entry (no subdomain wildcards, no IP literals).
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise DisallowedURLError(f"only https is allowed, got {parts.scheme!r}")
    if parts.username or parts.password:
        raise DisallowedURLError("credentials must not be embedded in URLs")
    try:
        port = parts.port
    except ValueError as exc:
        raise DisallowedURLError(f"invalid port in {url!r}") from exc
    if port not in (None, 443):
        raise DisallowedURLError(f"non-default port {port} is not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise DisallowedURLError("IP-literal hosts are not allowed")
    if host not in ALLOWED_HOSTS:
        raise DisallowedURLError(f"host {host!r} is not in the outbound allowlist")
    return url


def assert_public_address(host: str) -> list[str]:
    """Resolve ``host`` and fail if any address is private, loopback, link-local or reserved.

    Call this immediately before connecting, so a DNS answer cannot redirect a fetch to an
    internal service (SSRF). Returns the resolved addresses.
    """
    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        raise DisallowedURLError(f"{host!r} did not resolve")
    for addr in addresses:
        ip = ipaddress.ip_address(addr)
        if not ip.is_global:
            raise DisallowedURLError(f"{host!r} resolves to non-public address {addr}")
    return addresses
