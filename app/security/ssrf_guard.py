"""
app/security/ssrf_guard.py

Server-Side Request Forgery gate.

Every URL that enters GhostGrid's proxy must pass through validate_url_against_ssrf()
before a socket is opened. This is the last line of defense against an attacker
using GhostGrid to reach Render's internal network (169.254.169.254 cloud metadata,
127.0.0.1 localhost services, private RFC1918 ranges, IPv6 equivalents, etc.).

Contract:
    validate_url_against_ssrf(url) -> None       # raises ValueError on any SSRF risk
    resolve_and_verify_ip(hostname, port) -> List[str]  # returns verified-safe IPs
"""

import ipaddress
import logging
import socket
from typing import List
from urllib.parse import urlparse

logger = logging.getLogger("ghostgrid.ssrf")

# ---------------------------------------------------------------- networks

BLOCKED_IP_NETWORKS = [
    # IPv4
    ipaddress.ip_network("0.0.0.0/8"),          # "this network"
    ipaddress.ip_network("10.0.0.0/8"),          # private
    ipaddress.ip_network("100.64.0.0/10"),       # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),         # loopback
    ipaddress.ip_network("169.254.0.0/16"),      # link-local + cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),       # private
    ipaddress.ip_network("192.0.0.0/24"),        # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),        # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),      # private
    ipaddress.ip_network("198.18.0.0/15"),       # benchmark
    ipaddress.ip_network("198.51.100.0/24"),     # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),      # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),         # multicast
    ipaddress.ip_network("240.0.0.0/4"),         # reserved
    # IPv6
    ipaddress.ip_network("::/128"),              # unspecified
    ipaddress.ip_network("::1/128"),             # loopback
    ipaddress.ip_network("::ffff:0:0/96"),       # IPv4-mapped (dotted quad or hex can smuggle)
    ipaddress.ip_network("64:ff9b::/96"),        # NAT64
    ipaddress.ip_network("100::/64"),            # discard-only
    ipaddress.ip_network("2001::/32"),           # Teredo
    ipaddress.ip_network("2001:db8::/32"),       # doc
    ipaddress.ip_network("fc00::/7"),            # ULA
    ipaddress.ip_network("fe80::/10"),           # link-local
    ipaddress.ip_network("ff00::/8"),            # multicast
]

# Hostnames that must never be resolved (case-insensitive suffix/exact match).
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata",
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
    "instance-data.ec2.internal",
    "kubernetes.default",
    "kubernetes.default.svc",
}
BLOCKED_HOSTNAME_SUFFIXES = (".local", ".internal", ".localhost", ".arpa", ".svc", ".cluster.local")

# Ports that must never be reachable via the proxy.
BLOCKED_PORTS = {0, 22, 23, 25, 53, 135, 137, 138, 139, 445, 465, 587, 1433, 1521, 2049, 3306, 3389, 5432, 6379, 9200, 11211, 27017}


# ---------------------------------------------------------------- helpers

def _looks_like_ip_literal(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _normalize_hostname(hostname: str) -> str:
    """Lowercase, strip brackets (for IPv6 literals), and decode numeric-only hosts."""
    h = hostname.strip().lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    return h


def _resolve_numeric_ip(hostname: str):
    """
    Detect numeric-only hostnames that resolve to an IP using non-standard forms:
      - "2130706433"        -> 127.0.0.1     (decimal)
      - "0x7f000001"        -> 127.0.0.1     (hex)
      - "017700000001"      -> 127.0.0.1     (octal)
    These would otherwise bypass ipaddress.ip_address (which requires proper dots).
    """
    try:
        if hostname.startswith("0x") or hostname.startswith("0X"):
            return ipaddress.ip_address(int(hostname, 16))
        if hostname.isdigit():
            return ipaddress.ip_address(int(hostname))
        if hostname.startswith("0") and hostname[1:].isdigit():
            return ipaddress.ip_address(int(hostname, 8))
    except (ValueError, OverflowError):
        pass
    return None


# ---------------------------------------------------------------- core check

def _check_hostname(hostname: str) -> None:
    """Static hostname blocklist. Raises ValueError if forbidden."""
    if not hostname:
        raise ValueError("Empty hostname rejected (SSRF policy).")

    h = _normalize_hostname(hostname)

    if h in BLOCKED_HOSTNAMES:
        raise ValueError(f"Hostname '{hostname}' is on the SSRF blocklist.")

    for suffix in BLOCKED_HOSTNAME_SUFFIXES:
        if h.endswith(suffix):
            raise ValueError(f"Hostname '{hostname}' matches forbidden suffix '{suffix}'.")

    numeric = _resolve_numeric_ip(h)
    if numeric is not None:
        # Let the network check below catch it, but also short-circuit now.
        for net in BLOCKED_IP_NETWORKS:
            if numeric in net:
                raise ValueError(f"Numeric-hostname '{hostname}' resolves to prohibited IP {numeric}.")


def _check_ip(ip_str: str, hostname: str) -> None:
    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        raise ValueError(f"Unrecognized IP representation: {ip_str}")
    for net in BLOCKED_IP_NETWORKS:
        if ip_obj in net:
            raise ValueError(
                f"Host '{hostname}' resolved to prohibited IP '{ip_str}' "
                f"(matches {net})."
            )


def resolve_and_verify_ip(hostname: str, port: int = 443) -> List[str]:
    """
    DNS-resolve the hostname, verify every returned address, and return the safe set.
    Callers may use the returned list to pin subsequent connections (future work)
    and mitigate DNS-rebinding TOCTOU.
    """
    if not hostname:
        raise ValueError("Invalid target host: empty hostname.")
    if not (1 <= port <= 65535):
        raise ValueError(f"Invalid target port: {port}.")
    if port in BLOCKED_PORTS:
        raise ValueError(f"Port {port} is not permitted through the proxy.")

    _check_hostname(hostname)

    # If the hostname is already an IP literal, don't hit DNS.
    h = _normalize_hostname(hostname)
    if _looks_like_ip_literal(h):
        _check_ip(h, hostname)
        return [h]

    try:
        addr_info = socket.getaddrinfo(h, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failure for host '{hostname}': {exc}")

    safe_ips: List[str] = []
    for entry in addr_info:
        ip_str = entry[4][0]
        _check_ip(ip_str, hostname)
        if ip_str not in safe_ips:
            safe_ips.append(ip_str)

    if not safe_ips:
        raise ValueError(f"No resolvable addresses found for host '{hostname}'.")

    return safe_ips


def validate_url_against_ssrf(url: str) -> None:
    """Full gatekeeper. Raises ValueError on any SSRF risk; returns None on success."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Empty or non-string URL rejected.")

    parsed = urlparse(url.strip())

    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Prohibited URL scheme: '{parsed.scheme}'. Only http and https are allowed.")

    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not permitted through the proxy.")

    host = parsed.hostname
    if not host:
        raise ValueError("URL has no host component.")

    try:
        port = parsed.port
    except ValueError:
        raise ValueError("URL has a malformed port.")
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80

    resolve_and_verify_ip(host, port)