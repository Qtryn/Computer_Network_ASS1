"""Verify the Linux user-space TCP HTTP adapter in an isolated namespace."""
import http.client
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tests.test_server_control import tls_contexts


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _, context = tls_contexts(root)
        cert, private = root / "test-cert.pem", root / "test-key.pem"
        env = {**os.environ, "COLLAB_KEY": os.urandom(32).hex()}
        server = subprocess.Popen([sys.executable, "-B", "-m", "app.run_server", "--accounts",
                                   str(root / "accounts.json"), "--tls-cert", str(cert),
                                   "--tls-key", str(private), "--tcp-port", "28090",
                                   "--udp-port", "28091"], env=env)
        client = subprocess.Popen([sys.executable, "-B", "-m", "app.run_client", "--raw-http",
                                   "--ui-port", "28081", "--tcp-port", "28090", "--udp-port", "28091",
                                   "--server-name", "localhost", "--tls-ca", str(cert),
                                   "--ui-cert", str(cert), "--ui-key", str(private), "--state-db",
                                   str(root / "browser.sqlite3")], env=env)

        def request(path, body=None, cookie=None):
            conn = http.client.HTTPSConnection("localhost", 28081, timeout=6, context=context)
            try:
                headers = {"Content-Type": "application/json"}
                if cookie:
                    headers["Cookie"] = cookie
                conn.request("GET" if body is None else "POST", path, body, headers)
                response = conn.getresponse()
                result = response.status, response.read(), response.getheader("Set-Cookie")
                return result
            finally:
                conn.close()

        try:
            for attempt in range(3):
                try:
                    status, page, _ = request("/")
                    assert status == 200 and b"Collaboration App" in page
                    break
                except OSError:
                    if attempt == 2:
                        raise
                    time.sleep(0.2)
            credentials = json.dumps({"username": "raw_user", "password": "fixture-password"}).encode()
            assert request("/api/register", credentials)[0] == 200
            status, _, cookie = request("/api/login", credentials)
            assert status == 200 and cookie and "HttpOnly" in cookie
            browser_cookie = cookie.split(";", 1)[0]
            with ThreadPoolExecutor(max_workers=4) as workers:
                results = list(workers.map(lambda _: request("/api/state", cookie=browser_cookie), range(4)))
            assert all(status == 200 and json.loads(body)["connected"] for status, body, _ in results)
            print(f"PASS raw TCP HTTPS: {len(page)}-byte HTML, register/login, four concurrent API requests")
        finally:
            for process in (client, server):
                process.terminate()
                process.wait(timeout=8)


if __name__ == "__main__":
    main()
