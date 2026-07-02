"""Synchronous teardown for a ``QWebEngineView`` (GitHub #38).

PyQt6 + QtWebEngine crash with ``EXC_BAD_ACCESS`` (SIGBUS) **on quit** if a
web view is still wrapped when the interpreter finalises: SIP's ``atexit``
``cleanup_on_exit`` handler walks the wrapper graph and follows a pointer into
Chromium's already-released subtree (the crash backtrace shows
``cleanup_qobject → sip_api_visit_wrappers`` on ``CrBrowserMain``).

The obvious-looking ``view.deleteLater()`` + ``app.processEvents()`` drain is
**not** enough — and is in fact worse than doing nothing. ``processEvents()``
does not dispatch ``DeferredDelete`` events posted at the same loop level, and
at application quit the loop never spins again to flush them, so the view/page
C++ objects are never actually destroyed. They linger half-dead while the
default ``QWebEngineProfile`` is released underneath them, and QtWebEngine then
prints its own warning — ::

    Release of profile requested but WebEnginePage still not deleted.
    Expect troubles !

— right before the SIGBUS. This was reproduced 1:1 on Apple Silicon: a view
torn down with ``deleteLater()`` crashes at exit, the very same view destroyed
synchronously exits cleanly.

So we destroy the C++ objects **synchronously, now**, while Chromium is still
fully alive (which is when destruction is safe), via ``sip.delete()``. Call
this from a dialog's ``done()``/``closeEvent`` or a panel shutdown hook — any
point where the event loop is still running — and clear your own reference
afterwards. Idempotent and safe to call when WebEngine is absent (``view`` is
then ``None`` or a plain placeholder widget).
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QEventLoop, QTimer, QUrl
from PyQt6.QtWidgets import QApplication


def _sip_destroy(obj) -> bool:
    """Synchronously C++-delete ``obj`` via sip. Return ``True`` if, afterwards,
    the object is gone (already-deleted counts). ``False`` means sip can't act
    on it (sip missing, or ``obj`` isn't a wrapped Qt object — e.g. a test
    stub), so the caller should fall back to ``deleteLater``."""
    try:
        from PyQt6 import sip
    except ImportError:
        return False
    try:
        if sip.isdeleted(obj):
            return True
        sip.delete(obj)
        return True
    except (TypeError, ValueError, RuntimeError):
        return False


def _deferred_delete(obj) -> None:
    try:
        obj.setParent(None)
        obj.deleteLater()
    except (RuntimeError, AttributeError):
        pass


def drain_web_view(view) -> None:
    """Stop, blank and synchronously destroy ``view`` (and its owned page).

    ``view`` may be ``None`` (WebEngine unavailable) — then this is a no-op.
    """
    if view is None:
        return
    if not hasattr(view, "setUrl"):
        return  # placeholder QLabel shown when PyQt6-WebEngine is missing

    try:
        from PyQt6 import sip
        if sip.isdeleted(view):
            return
    except (ImportError, TypeError, ValueError):
        pass  # sip missing or view isn't a wrapped object (test stub)

    # 1. Cut signals and stop any in-flight load, then navigate to about:blank
    #    so Chromium tears its page down cleanly.
    try:
        view.loadFinished.disconnect()
    except (TypeError, RuntimeError):
        pass
    try:
        view.stop()
        view.setUrl(QUrl("about:blank"))
    except RuntimeError:
        pass

    # 2. Let about:blank settle so pending Chromium IPC drains.
    loop = QEventLoop()
    QTimer.singleShot(200, loop.quit)
    loop.exec()

    # 3. Grab the page (owned by the view) before we delete the view.
    try:
        page = view.page()
    except RuntimeError:
        page = None

    # 4. Destroy synchronously NOW. deleteLater() is not enough (see module
    #    docstring) — sip.delete() runs the C++ destructor immediately and
    #    invalidates the wrapper, so nothing survives to _Py_Finalize. Deleting
    #    the view also destroys its owned default page; we only fall back to a
    #    deferred delete if sip can't act on the object.
    if not _sip_destroy(view):
        _deferred_delete(view)
    if page is not None and not _sip_destroy(page):
        _deferred_delete(page)

    # 5. Flush any deferred deletes from the fallback path before returning.
    app = QApplication.instance()
    if app is not None:
        try:
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        except RuntimeError:
            pass
        for _ in range(3):
            app.processEvents()
