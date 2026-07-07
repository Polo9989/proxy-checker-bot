"""
Proxy string parser.  Handles every common format and auto-detects protocol.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from urllib.parse import urlparse


class ProxyProtocol(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class ProxyEntry:
    """Parsed, normalised proxy entry."""

    host: str
    port: int
    protocol: ProxyProtocol
    username: Optional[str] = None
    password: Optional[str] = None
    raw: str = ""

    # filled during checking
    working: Optional[bool] = None
    latency_ms: Optional[float] = None
    public_ip: Optional[str] = None
    error: Optional[str] = None

    @property
    def url(self) -> str:
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.protocol.value}://{auth}{self.host}:{self.port}"

    @property
    def has_auth(self) -> bool:
        return bool(self.username and self.password)


# ── helpers ────────────────────────────────────────────────────────────────────

_IP_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)
_PORT_RE = re.compile(r"^\d{1,5}$")


def _is_valid_ip(value: str) -> bool:
    return bool(_IP_RE.match(value))


def _is_valid_hostname(value: str) -> bool:
    if _is_valid_ip(value):
        return True
    parts = value.split(".")
    return all(
        part and all(c.isalnum() or c == "-" for c in part) for part in parts
    )


def _is_valid_port(value: str | int) -> bool:
    s = str(value)
    return _PORT_RE.match(s) is not None and 1 <= int(s) <= 65535


# ── main parser ───────────────────────────────────────────────────────────────

_SCHEME_PROTO: dict[str, ProxyProtocol] = {
    "http": ProxyProtocol.HTTP,
    "https": ProxyProtocol.HTTPS,
    "socks4": ProxyProtocol.SOCKS4,
    "socks5": ProxyProtocol.SOCKS5,
    "socks4a": ProxyProtocol.SOCKS4,
    "socks5h": ProxyProtocol.SOCKS5,
}


def parse_proxy(raw: str) -> Optional[ProxyEntry]:
    """
    Parse a single proxy string.  Returns *None* for clearly invalid input.

    Supported formats
    -----------------
    ip:port
    ip:port:user:pass
    user:pass@ip:port
    scheme://ip:port
    scheme://user:pass@ip:port
    """
    line = raw.strip()
    if not line or line.startswith("#"):
        return None

    protocol = ProxyProtocol.HTTP  # default
    username: Optional[str] = None
    password: Optional[str] = None

    # ── URI-style ──────────────────────────────────────────────────────────
    if "://" in line:
        try:
            parsed = urlparse(line)
        except Exception:
            return None
        scheme = (parsed.scheme or "").lower()
        if scheme not in _SCHEME_PROTO:
            return None
        protocol = _SCHEME_PROTO[scheme]
        host = parsed.hostname or ""
        port_raw = parsed.port
        username = parsed.username or None
        password = parsed.password or None
        if not host or port_raw is None:
            return None
        if not _is_valid_hostname(host) or not _is_valid_port(port_raw):
            return None
        return ProxyEntry(
            host=host,
            port=int(port_raw),
            protocol=protocol,
            username=username,
            password=password,
            raw=raw,
        )

    # ── user:pass@ip:port ──────────────────────────────────────────────────
    if "@" in line:
        creds, _, addr = line.rpartition("@")
        if ":" in creds:
            username, _, password = creds.partition(":")
        else:
            return None
        parts = addr.rsplit(":", 1)
        if len(parts) != 2:
            return None
        host, port_str = parts
        if not _is_valid_hostname(host) or not _is_valid_port(port_str):
            return None
        return ProxyEntry(
            host=host,
            port=int(port_str),
            protocol=protocol,
            username=username or None,
            password=password or None,
            raw=raw,
        )

    # ── ip:port  /  ip:port:user:pass ─────────────────────────────────────
    parts = line.split(":")
    if len(parts) == 2:
        host, port_str = parts
        if not _is_valid_hostname(host) or not _is_valid_port(port_str):
            return None
        return ProxyEntry(host=host, port=int(port_str), protocol=protocol, raw=raw)

    if len(parts) == 4:
        host, port_str, uname, pwd = parts
        if not _is_valid_hostname(host) or not _is_valid_port(port_str):
            return None
        return ProxyEntry(
            host=host,
            port=int(port_str),
            protocol=protocol,
            username=uname or None,
            password=pwd or None,
            raw=raw,
        )

    return None


def parse_proxy_list(text: str, limit: int = 100_000) -> tuple[list[ProxyEntry], list[str]]:
    """
    Parse multi-line proxy text.

    Returns
    -------
    valid   : list of ProxyEntry (up to *limit*)
    invalid : list of raw strings that failed parsing
    """
    valid: list[ProxyEntry] = []
    invalid: list[str] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        entry = parse_proxy(line)
        if entry is not None:
            valid.append(entry)
            if len(valid) >= limit:
                break
        else:
            invalid.append(line)

    return valid, invalid
