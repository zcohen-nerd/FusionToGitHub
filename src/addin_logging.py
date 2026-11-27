"""The add-in's log: file (rotating, owner-only on macOS), Fusion's text palette, redaction.

State lives in this module so every part of the add-in logs to the same
place. ``LOG_DIR`` is read at call time, so tests can point it at a temporary
folder. Only the palette handler touches the Fusion API, and only through the
``app`` object it is given.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import subprocess
import sys
import webbrowser
from typing import Optional

try:
    from fusion_git_core import redact_secrets
except ImportError:  # pragma: no cover - add-in folder not on sys.path yet
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fusion_git_core import redact_secrets

IS_WINDOWS = os.name == "nt"
LOG_DIR = os.path.expanduser("~/.PushToGitHub_AddIn_Data")
LOG_FILE_NAME = "PushToGitHub.log"
PRIVACY_URL = "https://github.com/zcohen-nerd/FusionToGitHub/blob/main/PRIVACY.md"
TITLE = "Push to GitHub"

logger: Optional[logging.Logger] = None
file_log_handler: Optional[logging.Handler] = None
fusion_palette_handler: Optional[logging.Handler] = None
current_log_level_name = "INFO"


def log_file_path() -> str:
    return os.path.join(LOG_DIR, LOG_FILE_NAME)


def _make_private(path: str) -> None:
    """Owner-only access on macOS/Linux; Windows user-profile folders are already private."""
    if IS_WINDOWS:
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


class RedactingFormatter(logging.Formatter):
    """Redacts the *finished* text, so tracebacks and child loggers are covered too."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record))


class _RedactSecretsFilter(logging.Filter):
    """Keep URL passwords and GitHub tokens out of the log file and palette (audit SEC-03/09)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            redacted = redact_secrets(message)
            if redacted != message:
                record.msg, record.args = redacted, None
        except Exception:
            pass
        return True


class _PrivateRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """A rotating log whose files are readable only by their owner on macOS/Linux."""

    def _open(self):
        stream = super()._open()
        _make_private(self.baseFilename)
        return stream


class FusionPaletteHandler(logging.Handler):
    """Logging handler that writes to Fusion's Text Commands palette via ``app.log``."""

    def __init__(self, app, log_levels=None):
        super().__init__()
        self._app = app
        self.LEVEL_MAP = {}
        if log_levels is None:
            return
        names = {
            logging.DEBUG: ("DebugLogLevel",),
            logging.INFO: ("InfoLogLevel", "Information"),
            logging.WARNING: ("WarningLogLevel", "Warning"),
            logging.ERROR: ("ErrorLogLevel", "Error"),
            logging.CRITICAL: ("CriticalLogLevel",),
        }
        for level, candidates in names.items():
            for candidate in candidates:
                value = getattr(log_levels, candidate, None)
                if value is not None:
                    self.LEVEL_MAP[level] = value
                    break

    def emit(self, record: logging.LogRecord) -> None:
        if not self._app:
            return
        try:
            message = self.format(record)
            if self.LEVEL_MAP:
                default_level = list(self.LEVEL_MAP.values())[0]
                self._app.log(message, self.LEVEL_MAP.get(record.levelno, default_level))
            else:
                self._app.log(message)
        except Exception:
            pass


def _ensure_log_dir_exists(app=None, log_levels=None) -> bool:
    if os.path.exists(LOG_DIR):
        return True
    try:
        os.makedirs(LOG_DIR, mode=0o700)
        return True
    except OSError as exc:
        msg = f"Error creating log directory {LOG_DIR}: {exc}"
        print(f"{msg}. Logging disabled.")
        if app:
            try:
                app.log(f"{msg}.", getattr(log_levels, "ErrorLogLevel", None))
            except Exception:
                pass
        return False


def setup_logger(name: str, app=None, log_levels=None, title: str = TITLE) -> logging.Logger:
    """Create (once) and return the add-in logger."""
    global logger, file_log_handler, fusion_palette_handler
    if logger is not None and logger.handlers:
        return logger

    if not _ensure_log_dir_exists(app, log_levels):
        logger = logging.getLogger(name + "_disabled")
        logger.addHandler(logging.NullHandler())
        return logger

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not any(isinstance(f, _RedactSecretsFilter) for f in logger.filters):
        logger.addFilter(_RedactSecretsFilter())
    # Files left by earlier versions become owner-only too.
    for existing_name in os.listdir(LOG_DIR):
        if existing_name.startswith(LOG_FILE_NAME):
            _make_private(os.path.join(LOG_DIR, existing_name))
    if not IS_WINDOWS:
        try:
            os.chmod(LOG_DIR, 0o700)
        except OSError:
            pass

    formatter = RedactingFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_log_handler = _PrivateRotatingFileHandler(
        log_file_path(),
        maxBytes=1 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_log_handler.setFormatter(formatter)
    logger.addHandler(file_log_handler)

    try:
        fusion_palette_handler = FusionPaletteHandler(app, log_levels)
        fusion_palette_handler.setFormatter(RedactingFormatter("%(levelname)s: %(message)s"))
        logger.addHandler(fusion_palette_handler)
    except Exception as exc:
        logger.warning(f"Could not initialize Fusion palette logging: {exc}")

    set_logger_level(current_log_level_name)
    logger.info(f"'{title}' Logger initialized. Log file: {log_file_path()}")
    return logger


def shutdown_logger() -> None:
    """Close and detach every handler (called from the add-in's stop())."""
    global logger, file_log_handler, fusion_palette_handler
    if logger:
        for handler in logger.handlers[:]:
            try:
                handler.close()
            finally:
                logger.removeHandler(handler)
    logger = None
    file_log_handler = None
    fusion_palette_handler = None


def set_logger_level(level_name: str) -> None:
    global current_log_level_name
    normalized = (level_name or "INFO").upper()
    current_log_level_name = normalized
    if not logger:
        return
    mapped_level = getattr(logging, normalized, logging.INFO)
    if file_log_handler:
        file_log_handler.setLevel(mapped_level)
    if fusion_palette_handler:
        fusion_palette_handler.setLevel(mapped_level)
    logger.debug("Logger level updated to %s", normalized)


def open_log_file(target_ui_ref, title: str = TITLE) -> None:
    path = log_file_path()
    if not os.path.exists(path):
        if target_ui_ref:
            target_ui_ref.messageBox("Log file not found yet. Run a push to generate logs first.", title)
        return
    try:
        if IS_WINDOWS:
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        if target_ui_ref:
            target_ui_ref.messageBox(
                f"Unable to open log file automatically.\nPath: {path}\nError: {exc}", title
            )
        if logger:
            logger.error("Failed to open log file: %s", exc, exc_info=True)


def clear_log_files(target_ui_ref, title: str = TITLE) -> None:
    """Delete the add-in's log files (the current one and its rotated copies)."""
    removed = 0
    errors = []
    handler = file_log_handler
    if handler:
        handler.acquire()
    try:
        if handler and getattr(handler, "stream", None):
            handler.stream.close()
            handler.stream = None  # reopened automatically on the next log line
        if os.path.isdir(LOG_DIR):
            for name in os.listdir(LOG_DIR):
                if name.startswith(LOG_FILE_NAME):
                    try:
                        os.remove(os.path.join(LOG_DIR, name))
                        removed += 1
                    except OSError as exc:
                        errors.append(f"{name}: {exc}")
    finally:
        if handler:
            handler.release()
    if target_ui_ref:
        if errors:
            target_ui_ref.messageBox("Some log files could not be deleted:\n" + "\n".join(errors), title)
        else:
            target_ui_ref.messageBox(f"Log cleared ({removed} file(s) deleted).", title)


def open_privacy_policy(target_ui_ref, title: str = TITLE) -> None:
    try:
        webbrowser.open(PRIVACY_URL)
    except Exception:
        if target_ui_ref:
            target_ui_ref.messageBox(f"Open this address in your browser:\n{PRIVACY_URL}", title)
