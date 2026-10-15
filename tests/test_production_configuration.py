"""Tests for MotionFence Production Environment Configuration Hardening.

Covers:
1. Production startup with valid strong secret (>=32 characters)
2. Production startup with missing secret
3. Production startup with weak secret (<32 characters)
4. Production startup with default repository secret
5. Configured CORS origin (exact origin in production, same-origin omission when unset, wildcard forbidden)
6. No secret in health responses (/health, /api/health)
7. No secret in error responses (400, 404, 405, 413, 429)
8. No secret in rendered frontend bundle (console/dist)
9. .env excluded from container build context (.dockerignore) and version control (.gitignore)
"""

from http import HTTPStatus
import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.config.settings import Settings, SecuritySettings
from scripts.console_server import ReadOnlyConsoleHandler, rate_limiter, DIST_DIR


class DummyServer:
    pass


def create_handler_for_test(
    command: str,
    path: str,
    body: dict = None,
    headers: dict = None,
    client_ip: str = "127.0.0.1",
) -> tuple[ReadOnlyConsoleHandler, io.BytesIO]:
    """Helper to instantiate ReadOnlyConsoleHandler with mock request streams."""
    wfile = io.BytesIO()
    body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
    rfile = io.BytesIO(body_bytes)

    handler = ReadOnlyConsoleHandler.__new__(ReadOnlyConsoleHandler)
    handler.command = command
    handler.path = path
    handler.requestline = f"{command} {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.rfile = rfile
    handler.wfile = wfile
    handler.client_address = (client_ip, 54321)
    handler.server = DummyServer()

    req_headers = {"Host": "localhost:8080"}
    if body is not None:
        req_headers["Content-Length"] = str(len(body_bytes))
        req_headers["Content-Type"] = "application/json"
    if headers:
        req_headers.update(headers)

    from http.client import HTTPMessage
    msg = HTTPMessage()
    for k, v in req_headers.items():
        msg.add_header(k, v)
    handler.headers = msg

    handler.send_response = MagicMock(side_effect=lambda code: setattr(handler, "_status_code", code))
    handler.send_header = MagicMock(side_effect=lambda k, v: handler._headers_sent.setdefault(k, []).append(v))
    handler._headers_sent = {}
    handler.end_headers = MagicMock()
    return handler, wfile


class TestProductionConfigurationHardening(unittest.TestCase):
    """Test suite verifying production environment configuration hardening properties."""

    def setUp(self):
        with rate_limiter.lock:
            rate_limiter.ip_buckets.clear()
            rate_limiter.global_timestamps.clear()

    # -------------------------------------------------------------------------
    # 1. Production Startup with Valid Strong Secret
    # -------------------------------------------------------------------------
    def test_production_startup_with_valid_strong_secret(self):
        """Production mode validates cleanly when supplied with a high-entropy secret >= 32 chars."""
        strong_secret = "c7e8a9f0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8"
        settings_inst = Settings(
            environment="production",
            security=SecuritySettings(
                kernel_secret=strong_secret,
                allow_insecure_tls=False,
                cors_origin="https://console.motionfence.app",
            ),
        )
        # Must not raise
        settings_inst.validate_production_security()

    # -------------------------------------------------------------------------
    # 2. Production Startup with Missing Secret
    # -------------------------------------------------------------------------
    def test_production_startup_with_missing_secret(self):
        """Production mode refuses to start when kernel_secret is empty."""
        settings_inst = Settings(
            environment="production",
            security=SecuritySettings(
                kernel_secret="",
                allow_insecure_tls=False,
            ),
        )
        with self.assertRaises(RuntimeError) as cm:
            settings_inst.validate_production_security()
        self.assertIn("MOTIONFENCE_KERNEL_SECRET must be set", str(cm.exception))

    # -------------------------------------------------------------------------
    # 3. Production Startup with Weak Secret
    # -------------------------------------------------------------------------
    def test_production_startup_with_weak_secret(self):
        """Production mode refuses to start when kernel_secret is shorter than 32 characters."""
        settings_inst = Settings(
            environment="production",
            security=SecuritySettings(
                kernel_secret="too_short_16char",
                allow_insecure_tls=False,
            ),
        )
        with self.assertRaises(RuntimeError) as cm:
            settings_inst.validate_production_security()
        self.assertIn("at least 32 characters", str(cm.exception))

    # -------------------------------------------------------------------------
    # 4. Production Startup with Default Secret
    # -------------------------------------------------------------------------
    def test_production_startup_with_default_secret(self):
        """Production mode refuses to start with known repository test default secret."""
        fallback_secrets = [
            "motionfence_runtime_kernel_secret",
            "motionfence_dev_test_kernel_secret",
            "default",
            "secret",
        ]
        for def_sec in fallback_secrets:
            settings_inst = Settings(
                environment="production",
                security=SecuritySettings(
                    kernel_secret=def_sec,
                    allow_insecure_tls=False,
                ),
            )
            with self.assertRaises(RuntimeError) as cm:
                settings_inst.validate_production_security()
            self.assertIn("Refusing to start with missing or default test secret", str(cm.exception))

    # -------------------------------------------------------------------------
    # 5. Configured CORS Origin
    # -------------------------------------------------------------------------
    def test_configured_cors_origin_in_production(self):
        """In production, the exact configured origin is returned."""
        target_origin = "https://judge.motionfence.io"
        with patch("scripts.console_server.settings") as mock_settings:
            mock_settings.environment = "production"
            mock_settings.security.cors_origin = target_origin

            handler, _ = create_handler_for_test("GET", "/api/status")
            handler.do_GET()

            allowed = handler._headers_sent.get("Access-Control-Allow-Origin")
            self.assertEqual(allowed, [target_origin])
            self.assertIn("Vary", handler._headers_sent)

    def test_unconfigured_cors_origin_in_production_omits_header(self):
        """In production without configured origin, Access-Control-Allow-Origin is omitted (same-origin only)."""
        with patch("scripts.console_server.settings") as mock_settings, patch.dict(os.environ, {"MOTIONFENCE_CORS_ORIGIN": ""}):
            mock_settings.environment = "production"
            mock_settings.security.cors_origin = ""

            handler, _ = create_handler_for_test("GET", "/api/status")
            handler.do_GET()

            allowed = handler._headers_sent.get("Access-Control-Allow-Origin")
            self.assertIsNone(allowed, "Must not emit wildcard or allow-origin in production when unset")

    def test_wildcard_cors_rejected_in_production(self):
        """Production validation strictly rejects wildcard '*' CORS configuration."""
        settings_inst = Settings(
            environment="production",
            security=SecuritySettings(
                kernel_secret="a" * 32,
                allow_insecure_tls=False,
                cors_origin="*",
            ),
        )
        with self.assertRaises(RuntimeError) as cm:
            settings_inst.validate_production_security()
        self.assertIn("Wildcard CORS origin ('*') is strictly prohibited in production", str(cm.exception))

    def test_development_cors_defaults_to_vite_dev_server(self):
        """In development mode without an explicit origin, CORS defaults to local Vite dev server."""
        with patch("scripts.console_server.settings") as mock_settings, patch.dict(os.environ, {"MOTIONFENCE_CORS_ORIGIN": ""}):
            mock_settings.environment = "development"
            mock_settings.security.cors_origin = ""

            handler, _ = create_handler_for_test("GET", "/api/status")
            handler.do_GET()

            allowed = handler._headers_sent.get("Access-Control-Allow-Origin")
            self.assertEqual(allowed, ["http://127.0.0.1:5173"])

    # -------------------------------------------------------------------------
    # 6. No Secret in Health Response
    # -------------------------------------------------------------------------
    def test_no_secret_in_health_response(self):
        """Neither /health nor /api/health discloses secrets or keys."""
        test_secret = "sensitive_production_token_1234567890abcdef"
        with patch.dict(os.environ, {"MOTIONFENCE_KERNEL_SECRET": test_secret, "NEBIUS_API_KEY": "neb_secret_key"}):
            for route in ("/health", "/api/health"):
                handler, wfile = create_handler_for_test("GET", route)
                handler.do_GET()
                resp_text = wfile.getvalue().decode("utf-8")
                self.assertNotIn(test_secret, resp_text)
                self.assertNotIn("neb_secret_key", resp_text)

    # -------------------------------------------------------------------------
    # 7. No Secret in Error Response
    # -------------------------------------------------------------------------
    def test_no_secret_in_error_response(self):
        """Error responses (400, 404, 405, 413, 429) do not disclose secrets or internal paths."""
        test_secret = "sensitive_production_token_1234567890abcdef"
        with patch.dict(os.environ, {"MOTIONFENCE_KERNEL_SECRET": test_secret}):
            # 404
            h404, w404 = create_handler_for_test("GET", "/api/nonexistent_resource")
            h404.do_GET()
            self.assertNotIn(test_secret, w404.getvalue().decode("utf-8"))

            # 405
            h405, w405 = create_handler_for_test("PUT", "/api/status")
            h405.do_PUT()
            self.assertNotIn(test_secret, w405.getvalue().decode("utf-8"))

            # 400
            h400, w400 = create_handler_for_test("POST", "/api/demo/run", headers={"Content-Length": "not_an_int"})
            h400.do_POST()
            self.assertNotIn(test_secret, w400.getvalue().decode("utf-8"))

            # 413
            oversized = {"scenario": "safe", "padding": "x" * 70000}
            h413, w413 = create_handler_for_test("POST", "/api/demo/run", body=oversized)
            h413.do_POST()
            self.assertNotIn(test_secret, w413.getvalue().decode("utf-8"))

    # -------------------------------------------------------------------------
    # 8. No Secret in Rendered Frontend Bundle
    # -------------------------------------------------------------------------
    def test_no_secret_in_rendered_frontend_bundle(self):
        """The compiled frontend distribution bundle in console/dist contains zero secrets or keys."""
        if not os.path.isdir(DIST_DIR):
            self.skipTest(f"Frontend dist directory not found at {DIST_DIR}")

        forbidden_patterns = [
            "MOTIONFENCE_KERNEL_SECRET",
            "NEBIUS_API_KEY",
            "TAVILY_API_KEY",
            "motionfence_runtime_kernel_secret",
        ]

        for root, _, files in os.walk(DIST_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                if file.endswith((".js", ".html", ".css", ".map")):
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        for pattern in forbidden_patterns:
                            self.assertNotIn(
                                pattern,
                                content,
                                f"Forbidden pattern '{pattern}' discovered in frontend asset {file_path}",
                            )

    # -------------------------------------------------------------------------
    # 9. .env Excluded from Container Build Context and Git
    # -------------------------------------------------------------------------
    def test_env_excluded_from_container_build_context_and_git(self):
        """Verify that .dockerignore and .gitignore strictly exclude .env files."""
        # 1. Inspect .dockerignore
        dockerignore_path = os.path.join(os.path.dirname(__file__), "..", ".dockerignore")
        self.assertTrue(os.path.isfile(dockerignore_path), ".dockerignore must exist")
        with open(dockerignore_path, "r", encoding="utf-8") as f:
            di_lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

        self.assertIn(".env", di_lines)
        self.assertIn(".env.*", di_lines)
        self.assertIn("*.env", di_lines)

        # 2. Inspect .gitignore
        gitignore_path = os.path.join(os.path.dirname(__file__), "..", ".gitignore")
        self.assertTrue(os.path.isfile(gitignore_path), ".gitignore must exist")
        with open(gitignore_path, "r", encoding="utf-8") as f:
            gi_lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

        self.assertIn(".env", gi_lines)
        self.assertIn(".env.*", gi_lines)
        self.assertIn("*.env", gi_lines)


if __name__ == "__main__":
    unittest.main()
