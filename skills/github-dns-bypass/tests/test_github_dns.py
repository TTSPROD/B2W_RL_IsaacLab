"""Behavioral checks requiring neither network access nor Git credentials."""

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "github_dns.py"
SPEC = importlib.util.spec_from_file_location("github_dns", SCRIPT)
dns = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dns)


class Response:
    def __init__(self, data=b"", status=200, headers=None):
        self.status = status
        self.stream = io.BytesIO(data)
        self.headers = headers or {}

    def read(self, count=-1):
        return self.stream.read(count)

    def getheader(self, name):
        return self.headers.get(name)


def connection(response=None, error=None):
    conn = mock.Mock()
    if error:
        conn.request.side_effect = error
    else:
        conn.getresponse.return_value = response
    return conn


class DirectTLSTests(unittest.TestCase):
    def test_connect_keeps_tls_identity_while_using_ip(self):
        context = mock.Mock()
        conn = dns.DirectHTTPSConnection("github.com", "1.1.1.1", context=context)
        raw_socket = mock.Mock()
        with mock.patch.object(dns.socket, "create_connection", return_value=raw_socket) as connect:
            conn.connect()
        connect.assert_called_once_with(("1.1.1.1", 443), 20)
        context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="github.com")

    def test_certificate_failure_closes_raw_socket(self):
        context = mock.Mock()
        context.wrap_socket.side_effect = ssl.SSLCertVerificationError("wrong hostname")
        conn = dns.DirectHTTPSConnection("github.com", "1.1.1.1", context=context)
        raw_socket = mock.Mock()
        with mock.patch.object(dns.socket, "create_connection", return_value=raw_socket):
            with self.assertRaises(ssl.SSLCertVerificationError):
                conn.connect()
        raw_socket.close.assert_called_once()

    def test_default_context_requires_verified_certificates(self):
        conn = dns.DirectHTTPSConnection("github.com", "1.1.1.1")
        self.assertTrue(conn._context.check_hostname)
        self.assertEqual(conn._context.verify_mode, ssl.CERT_REQUIRED)


class ResolveTests(unittest.TestCase):
    def test_provider_failure_falls_back_and_deduplicates_public_answers(self):
        first = connection(error=OSError("connection failed"))
        answer = {"Status": 0, "Answer": [
            {"type": 5, "data": "alias.github.com"},
            {"type": 1, "data": "1.1.1.1"},
            {"type": 1, "data": "1.1.1.1"},
            {"type": 1, "data": "8.8.8.8"},
        ]}
        second = connection(Response(json.dumps(answer).encode()))
        with mock.patch.object(dns, "DirectHTTPSConnection", side_effect=[first, second]) as ctor:
            self.assertEqual(dns.resolve("GitHub.COM."), ["1.1.1.1", "8.8.8.8"])
        self.assertEqual(ctor.call_args_list[0].args[:2], ("cloudflare-dns.com", "1.1.1.1"))
        self.assertEqual(ctor.call_args_list[1].args[:2], ("dns.google", "8.8.8.8"))
        self.assertIn("name=github.com&type=A", second.request.call_args.args[1])
        first.close.assert_called_once()
        second.close.assert_called_once()

    def test_private_or_missing_addresses_are_rejected(self):
        for answer in (
            {"Status": 0, "Answer": [{"type": 1, "data": "127.0.0.1"}]},
            {"Status": 0, "Answer": [{"type": 1, "data": "10.1.2.3"}]},
            {"Status": 3},
            {"Status": 0, "TC": True},
            {"Status": 0, "Answer": []},
        ):
            with self.subTest(answer=answer):
                conn = connection(Response(json.dumps(answer).encode()))
                with mock.patch.object(dns, "DirectHTTPSConnection", return_value=conn):
                    with self.assertRaises(dns.BypassError):
                        dns.resolve("github.com")

    def test_url_and_ip_are_not_accepted_as_hostname(self):
        for host in ("https://github.com", "github.com:443", "1.1.1.1", "github.com\r\nX:1"):
            with self.subTest(host=host), self.assertRaises(dns.BypassError):
                dns.resolve(host)


class DownloadTests(unittest.TestCase):
    def test_redirect_resolves_each_new_host_and_keeps_original_host(self):
        redirect = connection(Response(status=302, headers={
            "Location": "https://codeload.github.com/owner/repo/zip/commit"}))
        final = connection(Response(b"archive"))
        with mock.patch.object(dns, "resolve", return_value=["1.1.1.1"]) as resolver:
            with mock.patch.object(dns, "DirectHTTPSConnection", side_effect=[redirect, final]) as ctor:
                conn, response, url = dns.open_download("https://github.com/owner/repo/archive/commit.zip")
        self.assertIs(conn, final)
        self.assertEqual(response.read(), b"archive")
        self.assertTrue(url.startswith("https://codeload.github.com/"))
        self.assertEqual([call.args[0] for call in resolver.call_args_list], ["github.com", "codeload.github.com"])
        self.assertEqual([call.args[0] for call in ctor.call_args_list], ["github.com", "codeload.github.com"])
        redirect.close.assert_called_once()

    def test_relative_redirect_reuses_resolution(self):
        responses = [connection(Response(status=302, headers={"Location": "/new"})),
                     connection(Response(b"ok"))]
        with mock.patch.object(dns, "resolve", return_value=["1.1.1.1"]) as resolver:
            with mock.patch.object(dns, "DirectHTTPSConnection", side_effect=responses):
                conn, _, url = dns.open_download("https://github.com/old")
                conn.close()
        self.assertEqual(url, "https://github.com/new")
        resolver.assert_called_once_with("github.com", timeout=20)

    def test_redirect_to_http_or_unrelated_host_is_rejected(self):
        for target in ("http://github.com/repo", "https://evil.example/repo", "https://github.com.evil.example/repo"):
            with self.subTest(target=target):
                conn = connection(Response(status=302, headers={"Location": target}))
                with mock.patch.object(dns, "resolve", return_value=["1.1.1.1"]):
                    with mock.patch.object(dns, "DirectHTTPSConnection", return_value=conn):
                        with self.assertRaises(dns.BypassError):
                            dns.open_download("https://github.com/repo")
                conn.close.assert_called_once()

    def test_redirect_loop_is_bounded(self):
        conn = connection(Response(status=302, headers={"Location": "/loop"}))
        with mock.patch.object(dns, "resolve", return_value=["1.1.1.1"]):
            with mock.patch.object(dns, "DirectHTTPSConnection", return_value=conn) as ctor:
                with self.assertRaisesRegex(dns.BypassError, "Too many redirects"):
                    dns.open_download("https://github.com/loop", max_redirects=2)
        self.assertEqual(ctor.call_count, 3)

    def test_complete_download_atomically_replaces_existing_file(self):
        data = b"new vendor content"
        conn = mock.Mock()
        response = Response(data, headers={"Content-Length": str(len(data))})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifact.bin"
            output.write_bytes(b"old")
            with mock.patch.object(dns, "open_download", return_value=(conn, response, "https://github.com/final")):
                result = dns.download("https://github.com/artifact", output,
                                      expected_sha256=hashlib.sha256(data).hexdigest())
            self.assertEqual(output.read_bytes(), data)
            self.assertEqual(result["bytes"], len(data))
            self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(list(Path(directory).iterdir()), [output])
        conn.close.assert_called_once()

    def test_truncated_download_or_wrong_checksum_preserves_existing_file(self):
        for headers, expected in (({"Content-Length": "100"}, None), ({}, "0" * 64)):
            with self.subTest(headers=headers, expected=expected):
                conn = mock.Mock()
                response = Response(b"incomplete", headers=headers)
                with tempfile.TemporaryDirectory() as directory:
                    output = Path(directory) / "artifact.bin"
                    output.write_bytes(b"previous valid artifact")
                    with mock.patch.object(dns, "open_download", return_value=(conn, response, "https://github.com/a")):
                        with self.assertRaises(dns.BypassError):
                            dns.download("https://github.com/a", output, expected_sha256=expected)
                    self.assertEqual(output.read_bytes(), b"previous valid artifact")
                    self.assertEqual(list(Path(directory).iterdir()), [output])
                conn.close.assert_called_once()

    def test_midstream_failure_removes_partial_file(self):
        conn = mock.Mock()
        response = mock.Mock()
        response.getheader.return_value = None
        response.read.side_effect = [b"partial", OSError("network lost")]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifact.bin"
            with mock.patch.object(dns, "open_download", return_value=(conn, response, "https://github.com/a")):
                with self.assertRaises(OSError):
                    dns.download("https://github.com/a", output)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_credentials_and_nonstandard_ports_are_rejected(self):
        for url in ("https://token@github.com/repo", "https://github.com:444/repo"):
            with self.subTest(url=url), self.assertRaises(dns.BypassError):
                dns.validate_download_url(url)


class GitTests(unittest.TestCase):
    def test_process_receives_temporary_config_and_args_without_shell(self):
        with mock.patch.object(dns, "resolve", return_value=["1.1.1.1", "8.8.8.8"]):
            with mock.patch.object(dns.subprocess, "run", return_value=mock.Mock(returncode=7)) as run:
                with mock.patch.dict(os.environ, {"GIT_SSL_NO_VERIFY": "true"}):
                    result = dns.run_git(["--", "-C", "path with spaces", "push", "origin", "HEAD:refs/heads/topic"])
        self.assertEqual(result, 7)
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertIn("http.curloptResolve=github.com:443:1.1.1.1,8.8.8.8", command)
        self.assertIn("http.sslVerify=true", command)
        self.assertNotIn("http.sslBackend=openssl", command)
        self.assertEqual(command[-5:], ["-C", "path with spaces", "push", "origin", "HEAD:refs/heads/topic"])
        self.assertNotIn("GIT_SSL_NO_VERIFY", run.call_args.kwargs["env"])
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_optional_backend_is_explicit(self):
        command = dns.build_git_command(["fetch", "origin"], ["1.1.1.1"], ssl_backend="openssl")
        self.assertIn("http.sslBackend=openssl", command)

    def test_failed_mutation_is_not_automatically_retried(self):
        with mock.patch.object(dns, "resolve", return_value=["1.1.1.1"]):
            with mock.patch.object(dns.subprocess, "run", return_value=mock.Mock(returncode=128)) as run:
                self.assertEqual(dns.run_git(["push", "origin", "HEAD:refs/heads/topic"]), 128)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
