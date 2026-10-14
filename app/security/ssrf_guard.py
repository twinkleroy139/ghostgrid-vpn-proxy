import ipaddress
import socket
from urllib.parse import urlparse
from typing import List, Tuple

# Blocked IPv4 and IPv6 network subnets (RFC 1918, RFC 5735, RFC 3927, Cloud Metadata)
BLOCKED_IP_NETWORKS = [
    # IPv4 loopback & private ranges
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),      # Link-local & Cloud Metadata (AWS, GCP, Azure, DigitalOcean)
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),      # Carrier-grade NAT
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmark testing
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved
    # IPv6 loopback & private ranges
    ipaddress.ip_network("::1/128"),            # Loopback
    ipaddress.ip_network("fc00::/7"),           # Unique local address (ULA)
    ipaddress.ip_network("fe80::/10"),          # Link-local
    ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped IPv6
]


def resolve_and_verify_ip(hostname: str, port: int = 443) -> List[str]:
    """
    Performs DNS resolution on the hostname and verifies that NONE of the
    resolved IP addresses fall into private, loopback, or cloud-metadata subnets.
    Returns list of verified safe IP addresses.
    Raises ValueError on SSRF detection.
    """
    if not hostname:
        raise ValueError("Invalid target host: empty hostname.")

    # Reject raw localhost or cloud metadata aliases directly
    lowered = hostname.lower().strip("[]")
    if lowered in ("localhost", "metadata.google.internal", "instance-data"):
        raise ValueError(f"Target host '{hostname}' is forbidden (SSRF policy).")

    try:
        addr_info = socket.getaddrinfo(lowered, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failure for host '{hostname}': {exc}")

    safe_ips: List[str] = []

    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]

        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            raise ValueError(f"Unrecognized IP representation: {ip_str}")

        # Check against blocked networks
        for blocked_net in BLOCKED_IP_NETWORKS:
            if ip_obj in blocked_net:
                raise ValueError(
                    f"Access Denied: Host '{hostname}' resolved to prohibited IP '{ip_str}' "
                    f"(matches blocked range {blocked_net})."
                )

        if ip_str not in safe_ips:
            safe_ips.append(ip_str)

    if not safe_ips:
        raise ValueError(f"No resolvable addresses found for host '{hostname}'.")

    return safe_ips


def validate_url_against_ssrf(url: str) -> None:
    """
    Full SSRF gatekeeper function.
    Parses scheme, validates hostname, and checks resolved IPs against SSRF rules.
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Prohibited URL scheme: '{parsed.scheme}'. Only http and https allowed.")

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    resolve_and_verify_ip(parsed.hostname, port)