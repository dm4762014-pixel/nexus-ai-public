import io
import socket

import pytest

from nexus import network


def address(ip="93.184.216.34"):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))


@pytest.mark.parametrize("url", [
    "http://example.com", "file:///etc/passwd", "https://localhost/", "https://a.local/",
    "https://user:pass@example.com/", "https://example.com:8443", "https://example.com\\@localhost/",
    "https://example.com/\r\nHost:localhost", "https://[fe80::1%25eth0]/",
])
def test_bad_url_policy(url):
    with pytest.raises(network.NetworkRejected):
        network.validate_url(url)


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.169.254", "0.0.0.0", "224.0.0.1",
    "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1", "::ffff:8.8.8.8", "64:ff9b::7f00:1", "2002:7f00:1::",
])
def test_private_mapped_translation_and_multicast_rejected(monkeypatch, ip):
    monkeypatch.setattr(network.socket, "getaddrinfo", lambda *a, **kw: [address(ip)])
    with pytest.raises(network.NetworkRejected):
        network.validate_url("https://example.com")


def test_mixed_dns_rejected(monkeypatch):
    monkeypatch.setattr(network.socket, "getaddrinfo", lambda *a, **kw: [address(), address("127.0.0.1")])
    with pytest.raises(network.NetworkRejected):
        network.validate_url("https://example.com")


def test_pin_connect_uses_numeric_address_and_original_tls_hostname(monkeypatch):
    dns_calls, connected, sni = [], [], []
    monkeypatch.setattr(network.socket, "getaddrinfo", lambda *a, **kw: dns_calls.append(a) or [address()])
    destination = network.validate_url("https://EXAMPLE.com/path#fragment")

    class FakeSocket:
        def settimeout(self, timeout): pass
        def connect(self, target): connected.append(target)
        def getpeername(self): return ("93.184.216.34", 443)
        def close(self): pass
        def do_handshake(self): pass

    class FakeContext:
        def set_alpn_protocols(self, *args): pass
        def wrap_socket(self, raw, server_hostname, **kwargs):
            sni.append(server_hostname)
            return raw

    monkeypatch.setattr(network.ssl, "create_default_context", lambda: FakeContext())
    monkeypatch.setattr(network.socket, "socket", lambda *a: FakeSocket())
    connection = network._PinnedHTTPSConnection(destination, 3)
    connection.connect()
    assert len(dns_calls) == 1
    assert connected == [("93.184.216.34", 443)]
    assert sni == ["example.com"]
    assert destination["url"] == "https://example.com/path"


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b"hello"):
        self.status = status
        self.headers = headers or {"Content-Type": "text/html"}
        self.body = io.BytesIO(body)
    def getheader(self, name): return self.headers.get(name)
    def read(self, size): return self.body.read(size)


def fake_connections(monkeypatch, responses):
    class Connection:
        sock = None
        def __init__(self, *args): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return responses.pop(0)
        def close(self): pass
    monkeypatch.setattr(network.socket, "getaddrinfo", lambda *a, **kw: [address("127.0.0.1" if a[0] == "internal.example" else "93.184.216.34")])
    monkeypatch.setattr(network, "_PinnedHTTPSConnection", Connection)


def test_redirect_private_target_rejected(monkeypatch):
    fake_connections(monkeypatch, [FakeResponse(302, {"Location": "https://internal.example/secret"})])
    with pytest.raises(network.NetworkRejected, match="non-public"):
        network.fetch_public("https://example.com")


def test_public_redirect_is_revalidated(monkeypatch):
    fake_connections(monkeypatch, [FakeResponse(302, {"Location": "/new"}), FakeResponse(body=b"readable")])
    assert network.fetch_public("https://example.com")["url"] == "https://example.com/new"


@pytest.mark.parametrize("response", [
    FakeResponse(headers={"Content-Encoding": "br"}),
    FakeResponse(headers={"Content-Length": "9999999"}),
    FakeResponse(headers={"Content-Type": "application/octet-stream"}),
    FakeResponse(403), FakeResponse(429),
])
def test_unsafe_response_or_blocks_fail_closed(monkeypatch, response):
    fake_connections(monkeypatch, [response])
    with pytest.raises(network.NetworkRejected):
        network.fetch_public("https://example.com")


def test_stream_size_limit_without_content_length(monkeypatch):
    fake_connections(monkeypatch, [FakeResponse(body=b"X" * 1001)])
    with pytest.raises(network.NetworkRejected, match="download limit"):
        network.fetch_public("https://example.com", max_bytes=1000)


def test_gzip_is_incrementally_bounded(monkeypatch):
    import gzip
    headers = {"Content-Encoding": "gzip", "Content-Type": "text/html"}
    fake_connections(monkeypatch, [FakeResponse(headers=headers, body=gzip.compress(b"hello world"))])
    assert network.fetch_public("https://example.com")["body"] == b"hello world"
    fake_connections(monkeypatch, [FakeResponse(headers=headers, body=gzip.compress(b"X" * 100_000))])
    with pytest.raises(network.NetworkRejected, match="limit"):
        network.fetch_public("https://example.com", max_bytes=1000)
