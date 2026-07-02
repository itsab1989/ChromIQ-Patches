"""One-time warm-up of the QtWebEngine subsystem (issue #38 follow-up).

The **first** ``QWebEngineView`` ever created in the process pays the full cost
of spinning up Chromium's browser process and creating its first native
surface. On Windows that first-init pumps native events *synchronously*; when
it lands inside a modal dialog's show transition — the chart-design windows
(New chart / Add patches) building their 3D-cube preview on demand — it
reorders/recreates the parent editor window and wedges the modal grab. The app
appears to "reload the window" and then freezes. (macOS happens to tolerate the
same first-init mid-transition; Windows does not.)

Creating one hidden, throwaway view at startup pays that cost up front, on the
main event loop at idle and outside any modal, so every later in-dialog view is
cheap and side-effect-free. The view is kept alive for the whole session (a
lingering view is already expected — see :mod:`core.webengine_shutdown` and
``main._hard_exit``, which bypass CPython finalization on quit) and is never
shown.
"""
from __future__ import annotations

from core.logger import get_logger

log = get_logger(__name__)

# Module-global so the warm-up view is never garbage-collected; it must outlive
# every dialog so WebEngine-global state stays initialised for the session.
_warmup_view = None


def warm_up_webengine() -> None:
    """Create one hidden ``QWebEngineView`` so the process's costly first-init
    happens here, not inside a modal chart-design dialog.

    Idempotent; a no-op if PyQt6-WebEngine is unavailable. Must be called after
    the ``QApplication`` exists and, ideally, off the modal path (e.g. a
    ``QTimer.singleShot(0, ...)`` right after the main window is shown)."""
    global _warmup_view
    if _warmup_view is not None:
        return
    try:
        from PyQt6.QtCore import QUrl
        from PyQt6.QtWebEngineWidgets import QWebEngineView
    except ImportError:
        return  # WebEngine absent — 3D previews are disabled anyway
    try:
        view = QWebEngineView()           # no parent, never shown
        view.setUrl(QUrl("about:blank"))  # force the render process to spin up
        _warmup_view = view
        log.debug("QtWebEngine warmed up (hidden view created at startup)")
    except Exception:
        log.warning("WebEngine warm-up failed", exc_info=True)
