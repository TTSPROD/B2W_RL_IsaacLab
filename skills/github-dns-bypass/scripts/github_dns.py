#!/usr/bin/env python3
"""Verified HTTPS access to GitHub without depending on the system DNS resolver.

Python 3.9+, standard library only. No hosts-file, DNS, or global Git changes.
"""

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import tempfile
from urllib.parse import urlencode, urljoin, urlsplit


DOH_PROVIDERS = (
    ("cloudflare-dns.com", "1.1.1.1", "/dns-query"),
    ("dns.google", "8.8.8.8", "/resolve"),
)
GITHUB_HOSTS = {"github.com", "api.github.com", "codeload.github.com"}
USER_AGENT = "github-dns-bypass/1.0"
REDIRECT_CODES = {301, 302, 303, 307, 308}


class BypassError(Exception):
    """An actionable DNS, transport, URL, or integrity error."""


def normalize_host(host):
    host = host.rstrip(".").lower()
    labels = host.split(".")
    if len(host) > 253 or len(labels) < 2 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    ):
        raise BypassError("Expected a DNS hostname, without a URL, port, or credentials")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise BypassError("Expected a DNS hostname, not an IP address")


class DirectHTTPSConnection(http.client.HTTPSConnection):
    """Connect to an IP while verifying the certificate for the original host."""

    def __init__(self, host, ip, timeout=20, context=None):
        super().__init__(host, port=443, timeout=timeout,
                         context=context or ssl.create_default_context())
        self.connect_ip = str(ipaddress.ip_address(ip))

    def connect(self):
        # The numeric address never needs system hostname resolution. HTTP Host
        # and TLS server_hostname both remain self.host, not the numeric address.
        raw_socket = socket.create_connection((self.connect_ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except BaseException:
            raw_socket.close()
            raise


def resolve(host, timeout=20):
    """Resolve public IPv4 addresses via independently bootstrapped HTTPS DNS."""
    host = normalize_host(host)
    failures = []
    for provider_host, provider_ip, endpoint in DOH_PROVIDERS:
        conn = DirectHTTPSConnection(provider_host, provider_ip, timeout=timeout)
        try:
            conn.request("GET", endpoint + "?" + urlencode({"name": host, "type": "A"}),
                         headers={"Accept": "application/dns-json", "User-Agent": USER_AGENT})
            response = conn.getresponse()
            if response.status != 200:
                raise BypassError("HTTP " + str(response.status))
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise BypassError("DNS response is unexpectedly large")
            answer = json.loads(raw)
            if answer.get("Status") != 0 or answer.get("TC", False):
                raise BypassError("DNS query failed or response was truncated")
            addresses = []
            for record in answer.get("Answer", []):
                if record.get("type") != 1:
                    continue
                address = ipaddress.IPv4Address(record.get("data", ""))
                if not address.is_global:
                    raise BypassError("DNS returned a non-public address")
                value = str(address)
                if value not in addresses:
                    addresses.append(value)
            if not addresses:
                raise BypassError("No public IPv4 answer")
            return addresses
        except (OSError, ValueError, http.client.HTTPException, BypassError) as exc:
            failures.append(provider_host + ": " + str(exc))
        finally:
            conn.close()
    raise BypassError("DoH resolution failed for " + host + "; " + "; ".join(failures))


def validate_download_url(url):
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise BypassError("Invalid download URL") from exc
    if parts.scheme != "https" or not parts.hostname or port not in (None, 443):
        raise BypassError("Download and redirect URLs must use HTTPS on port 443")
    if parts.username is not None or parts.password is not None:
        raise BypassError("Credentials in download URLs are not supported")
    host = normalize_host(parts.hostname)
    if host not in GITHUB_HOSTS and not host.endswith(".githubusercontent.com"):
        raise BypassError("Download or redirect host is outside supported GitHub domains: " + host)
    return host, parts.path or "/", parts.query


def open_download(url, timeout=20, max_redirects=8):
    """Return an open (connection, response, final_url); caller owns connection."""
    cache = {}
    for hop in range(max_redirects + 1):
        host, path, query = validate_download_url(url)
        if host not in cache:
            cache[host] = resolve(host, timeout=timeout)
        last_error = None
        conn = None
        for ip in cache[host]:
            conn = DirectHTTPSConnection(host, ip, timeout=timeout)
            try:
                conn.request("GET", path + ("?" + query if query else ""),
                             headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
                response = conn.getresponse()
                break
            except (OSError, http.client.HTTPException) as exc:
                conn.close()
                last_error = exc
        else:
            raise BypassError("HTTPS connection failed for " + host + ": " + str(last_error))
        if response.status in REDIRECT_CODES:
            location = response.getheader("Location")
            conn.close()
            if not location:
                raise BypassError("Redirect is missing Location")
            if hop == max_redirects:
                raise BypassError("Too many redirects")
            url = urljoin(url, location)
            continue
        if response.status != 200:
            status = response.status
            conn.close()
            raise BypassError("Download failed with HTTP " + str(status))
        return conn, response, url
    raise BypassError("Too many redirects")


def download(url, output, timeout=20, expected_sha256=None):
    """Stream to a sibling temporary file, then atomically replace the output."""
    if expected_sha256 is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise BypassError("Expected SHA-256 must contain exactly 64 hexadecimal characters")
    # Validate before touching the filesystem.
    validate_download_url(url)
    target = Path(output).absolute()
    conn, response, final_url = open_download(url, timeout=timeout)
    temp_name = None
    digest = hashlib.sha256()
    count = 0
    try:
        content_length = response.getheader("Content-Length")
        expected_length = int(content_length) if content_length is not None else None
        if expected_length is not None and expected_length < 0:
            raise BypassError("Invalid Content-Length")
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="wb", prefix="." + target.name + ".",
                                         suffix=".part", dir=str(target.parent), delete=False) as stream:
            temp_name = stream.name
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                stream.write(chunk)
                digest.update(chunk)
                count += len(chunk)
            if expected_length is not None and count != expected_length:
                raise BypassError("Incomplete download: expected %d bytes, got %d" % (expected_length, count))
            if expected_sha256 is not None and digest.hexdigest() != expected_sha256.lower():
                raise BypassError("SHA-256 mismatch; existing output was preserved")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
        temp_name = None
    finally:
        conn.close()
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
    return {"output": str(target), "bytes": count, "sha256": digest.hexdigest(), "url": final_url}


def build_git_command(args, addresses, ssl_backend=None):
    if not args:
        raise BypassError("Pass Git arguments after 'git', for example: git ls-remote origin")
    ips = [str(ipaddress.IPv4Address(address)) for address in addresses]
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise BypassError("Git requires at least one public IPv4 address")
    # Empty curloptResolve resets inherited static mappings. A comma-separated
    # IP list lets libcurl try addresses without re-executing a mutating command.
    command = ["git", "-c", "http.sslVerify=true", "-c", "http.proxy=",
               "-c", "http.curloptResolve=", "-c",
               "http.curloptResolve=github.com:443:" + ",".join(ips)]
    if ssl_backend:
        command += ["-c", "http.sslBackend=" + ssl_backend]
    return command + list(args)


def run_git(args, timeout=20, ssl_backend=None):
    # Do not automatically retry subprocesses: a failed transport can still mean
    # that an upstream push completed. The skill describes reconciliation first.
    args = args[1:] if args and args[0] == "--" else args
    command = build_git_command(args, resolve("github.com", timeout=timeout), ssl_backend)
    environment = os.environ.copy()
    environment.pop("GIT_SSL_NO_VERIFY", None)
    return subprocess.run(command, env=environment, check=False).returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=20, help="Per-socket timeout in seconds (default: 20)")
    parser.add_argument("--ssl-backend", choices=("openssl", "schannel"),
                        help="Optional Git TLS backend, only if supported by this Git build")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    resolver = subparsers.add_parser("resolve", help="Print verified DoH IPv4 answers")
    resolver.add_argument("host")
    downloader = subparsers.add_parser("download", help="Download a public GitHub URL atomically")
    downloader.add_argument("url")
    downloader.add_argument("output")
    downloader.add_argument("--sha256", help="Expected SHA-256 digest")
    git_parser = subparsers.add_parser("git", help="Run Git once with per-command DNS overrides")
    git_parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        if args.mode == "resolve":
            print("\n".join(resolve(args.host, timeout=args.timeout)))
        elif args.mode == "download":
            print(json.dumps(download(args.url, args.output, timeout=args.timeout,
                                      expected_sha256=args.sha256), ensure_ascii=False))
        elif args.mode == "git":
            return run_git(args.args, timeout=args.timeout, ssl_backend=args.ssl_backend)
        return 0
    except (BypassError, OSError, ValueError, http.client.HTTPException) as exc:
        print("github-dns-bypass: " + str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
