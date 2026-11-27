"""Probe: can repository-local config run a program inside a token-carrying git process?

Isolated: no system/global config, fake host, fake token.
"""
import os
import subprocess
import sys
import tempfile

# The add-in's source in this repository (docs/audit/workpapers -> src), or a path given as an argument.
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "src")
sys.path.insert(0, SRC)

base = tempfile.mkdtemp(prefix="ftg_probe_")
empty_global = os.path.join(base, "global.gitconfig")
open(empty_global, "w").close()
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
os.environ["GIT_CONFIG_GLOBAL"] = empty_global

import fusion_git_core as core  # noqa: E402

repo = os.path.join(base, "repo")
os.makedirs(repo)
dump = os.path.join(base, "dump.txt").replace("\\", "/")


def g(*args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


g("init", "-q")
g("config", "user.name", "t")
g("config", "user.email", "t@example.invalid")
g("commit", "-q", "--allow-empty", "-m", "x")
g("remote", "add", "origin", "https://git.example.invalid/o/r.git")
# Malicious repository-local config
g("config", "url.ext::sh -c env>" + dump + " %S.insteadOf", "https://git.example.invalid/")
g("config", "url.ext::sh -c env>" + dump + " %S.pushInsteadOf", "https://git.example.invalid/")
g("config", "protocol.ext.allow", "always")

auth = core.token_auth("https://git.example.invalid/o/r.git", "FAKE_TOKEN_123", "")
# Since S4 a token is only given to git together with an empty hooks folder.
from dataclasses import replace  # noqa: E402
auth = replace(auth, hooks_dir=tempfile.mkdtemp(dir=base))
for name, args in (("ls-remote", ["ls-remote", "origin"]), ("push", ["push", "origin", "HEAD:refs/heads/x"])):
    if os.path.exists(dump):
        os.remove(dump)
    try:
        core.git_run(repo, *args, network=True, auth=auth, check=False)
    except Exception as exc:  # noqa: BLE001
        print(name, "raised", type(exc).__name__, str(exc)[:200])
    leaked = os.path.exists(dump) and "FAKE_TOKEN_123" in open(dump).read()
    print(name, "program ran:", os.path.exists(dump), "token visible:", leaked)
print("base", base)
