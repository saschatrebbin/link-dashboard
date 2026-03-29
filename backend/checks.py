"""
Monitoring checks for Link Dashboard.
Performs DNS lookup, host reachability, HTTP status, and SSL certificate checks.
"""

import socket
import ssl
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
import json

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


@dataclass
class CheckResult:
    """Result of a monitoring check."""

    dns_ips: list[str]
    host_reachable: bool
    http_status: Optional[int]
    http_response_time: Optional[float]  # milliseconds
    ssl_valid: bool
    ssl_issuer: Optional[str]
    ssl_sans: list[str]
    ssl_not_before: Optional[str]
    ssl_not_after: Optional[str]
    ssl_chain_valid: bool
    error_message: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    # Remove protocol
    domain = url.replace("http://", "").replace("https://", "").split("/")[0]
    # Remove port if present
    if ":" in domain:
        domain = domain.split(":")[0]
    return domain


def check_dns(url: str, port: int) -> tuple[list[str], Optional[str]]:
    """
    Perform DNS lookup for the domain.
    Returns (ips, error_message). Prefers IPv4 addresses.
    """
    domain = extract_domain(url)
    try:
        result = socket.getaddrinfo(domain, None)
        all_ips = [r[4][0] for r in result]
        # Separate IPv4 and IPv6
        ipv4_ips = [ip for ip in all_ips if ":" not in ip]
        ipv6_ips = [ip for ip in all_ips if ":" in ip]
        # Return IPv4 first, then IPv6
        ips = list(dict.fromkeys(ipv4_ips + ipv6_ips))
        return ips, None
    except socket.gaierror as e:
        return [], f"DNS resolution failed: {e}"
    except Exception as e:
        return [], f"DNS error: {e}"


def check_host_reachable(
    ips: list[str], port: int, timeout: float = 5.0
) -> tuple[bool, Optional[str]]:
    """
    Check if host is reachable via TCP connection.
    Tries IPv4 first, then IPv6.
    Returns (reachable, error_message).
    """
    ipv4_ips = [ip for ip in ips if ":" not in ip]
    ipv6_ips = [ip for ip in ips if ":" in ip]
    all_ips = ipv4_ips + ipv6_ips

    last_error = None
    for ip in all_ips:
        try:
            sock = socket.socket(
                socket.AF_INET if ":" not in ip else socket.AF_INET6, socket.SOCK_STREAM
            )
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            if result == 0:
                return True, None
            last_error = f"Connection to {ip} failed"
        except socket.timeout:
            last_error = f"Connection to {ip} timed out"
        except socket.error as e:
            last_error = f"Connection to {ip} failed: {e}"
        except Exception as e:
            last_error = f"Reachability check error for {ip}: {e}"

    return False, last_error


def check_http(
    url: str, port: int, timeout: float = 10.0
) -> tuple[Optional[int], Optional[float], Optional[str]]:
    """
    Perform HTTP/HTTPS request and return status code and response time.
    Returns (status_code, response_time_ms, error_message).
    """
    if not HAS_HTTPX:
        return None, None, "httpx not installed"

    # Build URL with port if non-standard
    if port == 443:
        full_url = url if url.startswith("https") else f"https://{extract_domain(url)}"
    elif port == 80:
        full_url = url if url.startswith("http") else f"http://{extract_domain(url)}"
    else:
        domain = extract_domain(url)
        protocol = "https" if port == 443 else "http"
        full_url = f"{protocol}://{domain}:{port}"

    try:
        start = time.time()
        with httpx.Client(
            verify=True, follow_redirects=True, timeout=timeout
        ) as client:
            response = client.get(full_url)
        response_time = (time.time() - start) * 1000  # Convert to ms
        return response.status_code, response_time, None
    except httpx.TimeoutException:
        return None, None, "Request timed out"
    except httpx.ConnectError as e:
        return None, None, f"Connection error: {e}"
    except httpx.SSLError as e:
        return None, None, f"SSL error: {e}"
    except Exception as e:
        return None, None, f"HTTP check error: {e}"


def check_ssl_certificate(domain: str, port: int = 443, timeout: float = 10.0) -> dict:
    """
    Retrieve and parse SSL certificate information.
    Returns dict with certificate details.
    """
    result = {
        "valid": False,
        "issuer": None,
        "sans": [],
        "not_before": None,
        "not_after": None,
        "chain_valid": False,
        "error": None,
    }

    if port != 443:
        result["error"] = "SSL check only on port 443"
        return result

    try:
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED

        with socket.create_connection((domain, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert(binary_form=True)

                if HAS_CRYPTO:
                    cert_obj = x509.load_der_x509_certificate(cert, default_backend())

                    # Issuer
                    issuer = cert_obj.issuer
                    issuer_parts = []
                    for attr in issuer:
                        if attr.oid == x509.NameOID.ORGANIZATION_NAME:
                            issuer_parts.append(attr.value)
                        elif attr.oid == x509.NameOID.COMMON_NAME:
                            issuer_parts.append(attr.value)
                    result["issuer"] = (
                        ", ".join(issuer_parts) if issuer_parts else str(issuer)
                    )

                    # Subject Alternative Names
                    try:
                        san_ext = cert_obj.extensions.get_extension_for_oid(
                            x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                        )
                        # Get all DNS names from the SAN extension
                        result["sans"] = [name.value for name in san_ext.value]
                    except (x509.ExtensionNotFound, AttributeError):
                        pass

                    # Validity dates
                    not_before = cert_obj.not_valid_before_utc
                    not_after = cert_obj.not_valid_after_utc
                    result["not_before"] = not_before.isoformat()
                    result["not_after"] = not_after.isoformat()

                    # Check if cert is currently valid
                    now = datetime.now(not_before.tzinfo)
                    result["valid"] = not_before <= now <= not_after
                else:
                    # Fallback without cryptography
                    import OpenSSL
                    from OpenSSL import SSL

                    # Basic extraction from raw cert
                    result["valid"] = True  # If we got this far, it's valid

                # Chain validation - basic check
                result["chain_valid"] = True  # httpx already validates the chain

    except ssl.SSLCertVerificationError as e:
        result["error"] = f"Certificate verification failed: {e}"
    except socket.timeout:
        result["error"] = "Connection timed out"
    except socket.gaierror:
        result["error"] = "DNS resolution failed"
    except Exception as e:
        result["error"] = f"SSL check error: {e}"

    return result


def perform_check(url: str, port: int = 443) -> dict:
    """
    Perform all monitoring checks for a URL.
    Returns a dict with all check results.
    """
    result = CheckResult(
        dns_ips=[],
        host_reachable=False,
        http_status=None,
        http_response_time=None,
        ssl_valid=False,
        ssl_issuer=None,
        ssl_sans=[],
        ssl_not_before=None,
        ssl_not_after=None,
        ssl_chain_valid=False,
        error_message=None,
    )

    errors = []
    domain = extract_domain(url)

    # DNS check
    dns_ips, dns_error = check_dns(url, port)
    result.dns_ips = dns_ips
    if dns_error:
        errors.append(dns_error)

    # Host reachability (try all IPs, prefer IPv4)
    if dns_ips:
        reachable, reach_error = check_host_reachable(dns_ips, port)
        result.host_reachable = reachable
        if reach_error:
            errors.append(reach_error)
    else:
        errors.append("No DNS resolution")
        result.host_reachable = False

    # HTTP check
    if result.host_reachable:
        http_status, response_time, http_error = check_http(url, port)
        result.http_status = http_status
        result.http_response_time = response_time
        if http_error:
            errors.append(http_error)

    # SSL check (only for HTTPS on port 443)
    if port == 443 and result.host_reachable:
        ssl_result = check_ssl_certificate(domain, port)
        result.ssl_valid = ssl_result["valid"]
        result.ssl_issuer = ssl_result["issuer"]
        result.ssl_sans = ssl_result["sans"]
        result.ssl_not_before = ssl_result["not_before"]
        result.ssl_not_after = ssl_result["not_after"]
        result.ssl_chain_valid = ssl_result["chain_valid"]
        if ssl_result["error"]:
            errors.append(ssl_result["error"])

    # Combine errors
    if errors:
        result.error_message = "; ".join(errors)

    return result.to_dict()


def detect_changes(old_result: Optional[dict], new_result: dict) -> list[dict]:
    """
    Compare old and new check results and detect changes.
    Returns list of change records.
    """
    changes = []

    if old_result is None:
        return changes

    # DNS changes
    old_ips = set(old_result.get("dns_ips", []) or [])
    new_ips = set(new_result.get("dns_ips", []) or [])
    if old_ips != new_ips:
        changes.append(
            {
                "type": "dns",
                "old": list(old_ips),
                "new": list(new_ips),
                "description": f"DNS changed: {old_ips} -> {new_ips}",
            }
        )

    # SSL certificate changes
    old_ssl_after = old_result.get("ssl_not_after")
    new_ssl_after = new_result.get("ssl_not_after")
    old_ssl_issuer = old_result.get("ssl_issuer")
    new_ssl_issuer = new_result.get("ssl_issuer")

    if old_ssl_issuer != new_ssl_issuer:
        changes.append(
            {
                "type": "ssl_issuer",
                "old": old_ssl_issuer,
                "new": new_ssl_issuer,
                "description": f"SSL issuer changed: {old_ssl_issuer} -> {new_ssl_issuer}",
            }
        )

    if old_ssl_after != new_ssl_after:
        changes.append(
            {
                "type": "ssl_expiry",
                "old": old_ssl_after,
                "new": new_ssl_after,
                "description": f"SSL expiry changed: {old_ssl_after} -> {new_ssl_after}",
            }
        )

    return changes


def get_status_indicator(result: dict) -> str:
    """
    Get status indicator based on check results.
    Returns: 'ok', 'warn', or 'error'
    """
    if (
        result.get("error_message")
        and "DNS resolution failed" in result["error_message"]
    ):
        return "error"

    if not result.get("host_reachable"):
        return "error"

    http_status = result.get("http_status")
    if http_status:
        if 200 <= http_status < 300:
            return "ok"
        elif 400 <= http_status < 500:
            return "warn"  # Client error - might be intentional
        elif http_status >= 500:
            return "error"  # Server error

    ssl_valid = result.get("ssl_valid")
    if ssl_valid is False:
        return "error"

    # Check if SSL cert expires soon (within 7 days)
    ssl_not_after = result.get("ssl_not_after")
    if ssl_not_after:
        try:
            from datetime import datetime

            expiry = datetime.fromisoformat(ssl_not_after.replace("Z", "+00:00"))
            days_until_expiry = (expiry - datetime.now()).days
            if days_until_expiry < 0:
                return "error"
            elif days_until_expiry < 7:
                return "warn"
        except:
            pass

    return "ok"


if __name__ == "__main__":
    # Test with a known URL
    import sys

    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.google.com"
    test_port = int(sys.argv[2]) if len(sys.argv) > 2 else 443

    print(f"Checking {test_url}:{test_port}...")
    result = perform_check(test_url, test_port)
    print(json.dumps(result, indent=2))
    print(f"\nStatus: {get_status_indicator(result)}")
