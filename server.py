"""
server.py - Improved version with .git exclusion
Put this file in your GitHub repo.
"""

import http.server
import hmac
import hashlib
import json
import os
import subprocess
import threading

PORT = 5000
REPO_DIR = os.path.dirname(os.path.abspath(__file__))

# Secret is loaded from /var/www/.env
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").encode()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
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

        # Pull and restart in background
        threading.Thread(target=self._pull_and_restart, daemon=True).start()

    def _pull_and_restart(self):
        import time
        time.sleep(0.5)

        print("[webhook] Force pulling latest from GitHub...")

        try:
            # Main git commands
            subprocess.run(["git", "fetch", "--all"], cwd=REPO_DIR, check=True)
            subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=REPO_DIR, check=True)
            
            # Extra security: Remove .git folder if it somehow appears
            git_dir = os.path.join(REPO_DIR, ".git")
            if os.path.exists(git_dir):
                print("[webhook] Removing exposed .git folder for security...")
                subprocess.run(["rm", "-rf", git_dir], check=True)

            print("[webhook] Pull done and .git cleaned. Exiting so launcher restarts us...")
            os._exit(0)

        except Exception as e:
            print(f"[webhook] Error during pull: {e}")
            os._exit(1)


if __name__ == "__main__":
    print(f"[server] Serving on port {PORT} from {REPO_DIR}")
    print(f"[server] Webhook listening at /webhook")
    with http.server.HTTPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()
