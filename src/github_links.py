"""Links to a backup on GitHub, and copying text to the clipboard (audit UX-05). No Fusion dependency."""

from __future__ import annotations

import os
import subprocess
from typing import Optional
from urllib.parse import quote, urlsplit

GITHUB_HOST = "github.com"


def web_repository_url(remote_url: str) -> Optional[str]:
    """The repository's web page for a Git address, or None if it can't be worked out.

    ``https://github.com/acme/designs.git`` and ``git@github.com:acme/designs.git``
    both give ``https://github.com/acme/designs``. Addresses with a user name or
    password, other schemes, or no owner/name are refused.
    """
    url = (remote_url or "").strip()
    if not url:
        return None
    if "://" not in url and url.startswith("git@") and ":" in url:
        host, _, path = url[len("git@"):].partition(":")
        scheme_host = f"https://{host.lower()}"
    else:
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            return None
        if parts.scheme.lower() not in ("https", "http", "ssh") or not parts.hostname:
            return None
        if parts.password:
            return None
        host = parts.hostname.lower()
        if parts.scheme.lower() != "ssh" and port:
            host += f":{port}"
        scheme_host = f"https://{host}"
        path = parts.path
    path = path.strip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    segments = [s for s in path.split("/") if s]
    if len(segments) < 2 or any(s in (".", "..") for s in segments):
        return None
    return scheme_host + "/" + "/".join(quote(s, safe="") for s in segments)


def is_github(remote_url: str) -> bool:
    web = web_repository_url(remote_url)
    return bool(web) and urlsplit(web).hostname == GITHUB_HOST


def folder_url(remote_url: str, branch: str, folder: str = "") -> Optional[str]:
    """A link to *folder* on *branch*, for github.com; the repository page for other servers.

    Other servers lay out their pages differently, so only the repository
    page is offered for them. None when the address isn't a web repository.
    """
    web = web_repository_url(remote_url)
    if not web:
        return None
    if not is_github(remote_url) or not branch:
        return web
    link = f"{web}/tree/{quote(branch, safe='/')}"
    folder = (folder or "").strip("/")
    if folder:
        link += "/" + "/".join(quote(part, safe="") for part in folder.split("/") if part)
    return link


def copy_to_clipboard(text: str) -> bool:
    """Put *text* on the system clipboard. False if that isn't possible here.

    Uses the operating system's own tool (``clip`` on Windows, ``pbcopy`` on
    macOS), so no extra Python packages are needed.
    """
    if not text:
        return False
    if os.name == "nt":
        # clip.exe recognises UTF-16LE input (checked on Windows 11); with a
        # byte-order mark it would copy the mark too.
        command, data = ["clip"], text.encode("utf-16-le")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        command, data, flags = ["pbcopy"], text.encode("utf-8"), 0
    try:
        proc = subprocess.run(command, input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=5, creationflags=flags)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


__all__ = ["copy_to_clipboard", "folder_url", "is_github", "web_repository_url"]
