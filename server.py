"""
server.py - zman website server + GitHub webhook
"""

import http.server
import hmac
import hashlib
import json
import os
import subprocess
import sys
import threading

PORT = 5000
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
WEBHOOK_SECRET = b"REPLACE_WITH_YOUR_SECRET"  # must match GitHub webhook secret


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve files from the repo directory
        super().__init__(*args, directory=REPO_DIR, **kwargs)

    def do_POST(self):
        if self.path == "/webhook":
            self._handle_webhook()
        else:
            self.send_error(404)

    def _handle_webhook(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        # Verify GitHub signature
        sig_header = self.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(sig_header, expected):
            print("[webhook] Rejected: bad signature")
            self.send_response(403)
            self.end_headers()
            return

        payload = json.loads(body)
        branch = payload.get("ref", "")

        if branch != "refs/heads/main":
            print(f"[webhook] Ignored push to {branch}")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ignored")
            return

        print("[webhook] Push to main detected — pulling and restarting...")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

        # Pull and signal launcher to restart (done in background so response sends first)
        threading.Thread(target=self._pull_and_restart, daemon=True).start()

    def _pull_and_restart(self):
        import time
        time.sleep(0.5)  # let the HTTP response flush
        subprocess.run(["git", "pull"], cwd=REPO_DIR)
        print("[webhook] Pull done. Exiting so launcher restarts us...")
        # Exit this process — launcher.py will detect the exit and restart
        os._exit(0)

    def log_message(self, format, *args):
        print(f"[http] {self.address_string()} - {format % args}")


if __name__ == "__main__":
    print(f"[server] Serving on port {PORT} from {REPO_DIR}")
    print(f"[server] Webhook listening at /webhook")
    with http.server.HTTPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()
