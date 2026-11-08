"""HTTPS-only retrieval with numeric socket pinning and original-host TLS SNI.

No proxy, cookies, authentication or unbounded decompression. Each redirect
requires new DNS validation and a new pinned connection.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import threading
import time
import zlib
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

MAX_DOWNLOAD = 2_000_000
MAX_REDIRECTS = 3
TIMEOUT = 8


class NetworkRejected(ValueError):
    """Destination or response violates the retrieval policy."""


def _public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
        if not address.is_global or address.is_multicast:
            return False
        if isinstance(address, ipaddress.IPv6Address):
            if address.ipv4_mapped or address.sixtofour or address.teredo:
                return False
            if address in ipaddress.ip_network("64:ff9b::/96") or address in ipaddress.ip_network("64:ff9b:1::/48"):
                return False
        return True
    except ValueError:
        return False


def validate_url(url: str) -> dict:
    """Return normalized URL, TLS hostname and immutable resolved addresses.

    Callers must connect to numeric addresses rather than resolving the hostname
    again. Mixed public/private DNS answers fail closed.
    """
    if not isinstance(url, str) or not 1 <= len(url) <= 2048:
        raise NetworkRejected("URL must contain 1-2048 characters")
    if any(ord(c) < 33 or ord(c) == 127 for c in url) or "\\" in url:
        raise NetworkRejected("Control characters, spaces and backslashes are forbidden")
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise NetworkRejected("Only public HTTPS destinations are allowed")
        if parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
            raise NetworkRejected("URL credentials and nonstandard ports are forbidden")
        hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        if "%" in hostname or hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal", ".home", ".lan")):
            raise NetworkRejected("Local hostnames and IPv6 zones are forbidden")
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        if not addresses or any(not _public_ip(item[4][0]) for item in addresses):
            raise NetworkRejected("DNS resolves to a non-public or translated network address")
        netloc = f"[{hostname}]" if ":" in hostname else hostname
        path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
        query = quote(parsed.query, safe="/%?:@!$&'()*+,;=-._~")
        normalized = urlunsplit(("https", netloc, path, query, ""))
        return {"url": normalized, "hostname": hostname, "addresses": tuple(addresses), "target": path + ("?" + query if query else "")}
    except (UnicodeError, OSError, ValueError) as exc:
        if isinstance(exc, NetworkRejected):
            raise
        raise NetworkRejected(f"Invalid or unresolvable destination: {type(exc).__name__}") from exc


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, destination: dict, timeout: float):
        super().__init__(destination["hostname"], port=443, timeout=timeout, context=ssl.create_default_context())
        self.destination = destination

    def connect(self):
        last_error = None
        deadline = time.monotonic() + self.timeout
        for family, socktype, proto, _, address in self.destination["addresses"]:
            raw = socket.socket(family, socktype, proto)
            try:
                self._pinned_socket = raw
                raw.settimeout(max(0.1, deadline - time.monotonic()))
                raw.connect(address)  # numeric sockaddr; no second DNS lookup
                if not _public_ip(raw.getpeername()[0]):
                    raise NetworkRejected("Connected peer is not public")
                self.sock = self._context.wrap_socket(raw, server_hostname=self.host, do_handshake_on_connect=False)
                self._pinned_socket = self.sock
                self.sock.settimeout(max(0.1, deadline - time.monotonic()))
                self.sock.do_handshake()
                return
            except Exception as exc:
                raw.close()
                last_error = exc
                if time.monotonic() >= deadline:
                    break
        raise NetworkRejected(f"HTTPS connection failed: {type(last_error).__name__}") from last_error


def fetch_public(url: str, *, max_bytes: int = MAX_DOWNLOAD, timeout: float = TIMEOUT, checkpoint=None) -> dict:
    """Read bounded HTML/text/PDF bytes, including bounded gzip/deflate."""
    if not 1 <= max_bytes <= MAX_DOWNLOAD or not 0 < timeout <= 20:
        raise ValueError("Fetch limits exceed policy")
    deadline = time.monotonic() + timeout
    visited = set()
    for _ in range(MAX_REDIRECTS + 1):
        if checkpoint:
            checkpoint()
        if time.monotonic() >= deadline:
            raise NetworkRejected("Retrieval time limit exceeded")
        destination = validate_url(url)
        if destination["url"] in visited:
            raise NetworkRejected("Redirect loop")
        visited.add(destination["url"])
        connection = _PinnedHTTPSConnection(destination, max(0.1, deadline - time.monotonic()))
        def abort_connection(connection=connection):
            pinned = getattr(connection, "_pinned_socket", None)
            if pinned:
                try:
                    pinned.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                pinned.close()
        # A socket timeout alone does not stop a slow peer sending one byte at
        # a time. Closing the owned socket enforces the complete-fetch deadline.
        timer = threading.Timer(max(0.1, deadline - time.monotonic()), abort_connection)
        timer.daemon = True
        timer.start()
        try:
            connection.request("GET", destination["target"], headers={
                "User-Agent": "NEXUSAI-Research/1.0 (+local evidence retrieval)",
                "Accept": "text/html,application/pdf,text/plain;q=0.8",
                "Accept-Encoding": "identity", "Connection": "close",
            })
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise NetworkRejected("Redirect has no destination")
                url = urljoin(destination["url"], location)
                continue
            if response.status != 200:
                raise NetworkRejected(f"Source returned HTTP {response.status}; access restrictions respected")
            encoding = (response.getheader("Content-Encoding") or "identity").lower().strip()
            if encoding not in ("", "identity", "gzip", "deflate"):
                raise NetworkRejected("Unsupported HTTP content encoding")
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS) if encoding in ("gzip", "deflate") else None
            declared = response.getheader("Content-Length")
            if declared is not None and (not declared.isdecimal() or int(declared) > max_bytes):
                raise NetworkRejected("Invalid or oversized response Content-Length")
            content_type = (response.getheader("Content-Type") or "").lower().split(";", 1)[0].strip()
            if content_type not in ("text/html", "application/xhtml+xml", "application/pdf", "text/plain"):
                raise NetworkRejected(f"Unsupported response type: {content_type or 'missing'}")
            body = bytearray()
            wire_bytes = 0
            while True:
                if checkpoint:
                    checkpoint()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise NetworkRejected("Retrieval time limit exceeded")
                if connection.sock:
                    connection.sock.settimeout(max(0.1, remaining))
                read = getattr(response, "read1", response.read)
                block = read(min(32_768, max_bytes + 1 - wire_bytes))
                if not block:
                    break
                wire_bytes += len(block)
                if wire_bytes > max_bytes:
                    raise NetworkRejected("Response exceeds bounded download limit")
                if decoder:
                    block = decoder.decompress(block, max_bytes + 1 - len(body))
                    if decoder.unconsumed_tail or decoder.unused_data:
                        raise NetworkRejected("Compressed response exceeds decoded limit or contains extra streams")
                body.extend(block)
                if len(body) > max_bytes:
                    raise NetworkRejected("Response exceeds bounded download limit")
            if decoder and not decoder.eof:
                raise NetworkRejected("Truncated compressed response")
            return {"url": destination["url"], "body": bytes(body), "content_type": content_type,
                    "retrieved_at": time.time(), "bytes": len(body)}
        except (OSError, http.client.HTTPException, zlib.error) as exc:
            raise NetworkRejected(f"Source unavailable: {type(exc).__name__}") from exc
        finally:
            timer.cancel()
            connection.close()
    raise NetworkRejected("Too many redirects")
