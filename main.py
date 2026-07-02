"""ChromIQ Patches — standalone chart patch-set / layout designer.  Entry point.

The app is ChromIQ's "Edit / create chart patch set" tool (Knut's patch
generators + the ChromIQ layout engine + i1Profiler export) cut loose from the
full profiling suite. The boot sequence below mirrors ChromIQ's main.py — the
early logging, faulthandler, WebEngine pre-import and hard-exit teardown all
exist for the same reasons documented there (issues #11/#13/#38 upstream).
"""
from __future__ import annotations

import logging
import os
import sys
import traceback

# Configure logging FIRST, before any heavy third-party imports (PyQt6, numpy,
# etc.) — a frozen bundle with a broken dylib graph must still leave a trace.
from core.logger import configure_logging, get_logger

configure_logging()
log = get_logger("chromiq-patches")


def _log_excepthook(exc_type, exc, tb):
    log.critical(
        "Uncaught exception:\n%s",
        "".join(traceback.format_exception(exc_type, exc, tb)),
    )
    sys.__excepthook__(exc_type, exc, tb)


sys.excepthook = _log_excepthook

# Native crash capture — fatal signals inside Qt/Chromium teardown never reach
# the excepthook above; faulthandler dumps every thread's stack to our own log
# directory instead. Kept at module scope so the fd stays open for the process
# lifetime.
import faulthandler  # noqa: E402

_crash_log = None
try:
    from datetime import datetime as _dt

    from core.platform_paths import log_dir as _log_dir

    _crash_dir = _log_dir()
    _crash_dir.mkdir(parents=True, exist_ok=True)
    _crash_log = open(_crash_dir / "chromiq-patches-crash.log", "a", encoding="utf-8")
    _crash_log.write(f"\n=== faulthandler armed {_dt.now():%Y-%m-%d %H:%M:%S} ===\n")
    _crash_log.flush()
    faulthandler.enable(file=_crash_log, all_threads=True)
except Exception:
    log.debug("Could not arm faulthandler to crash log; using stderr", exc_info=True)
    faulthandler.enable()

log.info(
    "ChromIQ Patches starting; python=%s platform=%s frozen=%s argv=%s",
    sys.version.split()[0],
    sys.platform,
    getattr(sys, "frozen", False),
    sys.argv,
)

if sys.platform == "win32":
    # Own taskbar identity before any window exists (see ChromIQ main.py).
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ChromIQ.Patches"
        )
    except Exception:
        log.debug("Could not set Windows AppUserModelID", exc_info=True)

    # Windows ARM: re-enable WebGL past the GPU blocklist, keep the software
    # compositor so the bypass doesn't break rendering.
    _existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    _extra = "--ignore-gpu-blocklist --disable-gpu-compositing"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{_existing} {_extra}".strip()

try:
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    # QtWebEngine must be imported before QApplication is instantiated.
    # Optional: without it only the 3D patch-cube preview is disabled.
    try:
        import PyQt6.QtWebEngineWidgets  # noqa: F401
    except ImportError:
        log.warning("QtWebEngine not available — 3D patch cube will be disabled")

    from PyQt6.QtGui import QFontDatabase
    from core.argyll_runner import ArgyllRunner
    from core.resource_path import resource_path
    from core.settings import AppSettings
    from ui.dialogs.ti2_relayout_dialog import Ti2RelayoutDialog
    from ui.styles import WinButtonLayoutStyle
    from ui.theme import apply_appearance
    from ui.widgets import ButtonFontFilter, GroupBoxSurfaceFilter, TooltipWrapFilter
except BaseException:
    log.exception("Fatal error importing application modules")
    raise


def main() -> int:
    from core.version import APP_VERSION

    app = QApplication(sys.argv)
    app.setApplicationName("ChromIQ Patches")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("ChromIQ")
    app.setApplicationDisplayName("ChromIQ Patches — Chart Designer")

    try:
        for font_path in resource_path("assets/fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font_path))
    except Exception:
        pass  # fonts dir missing — app falls back to system fonts

    app.setStyle(WinButtonLayoutStyle("Fusion"))

    _btn_font_filter = ButtonFontFilter(app)
    app.installEventFilter(_btn_font_filter)

    _gb_surface_filter = GroupBoxSurfaceFilter(app)
    app.installEventFilter(_gb_surface_filter)

    _tooltip_wrap_filter = TooltipWrapFilter(app)
    app.installEventFilter(_tooltip_wrap_filter)

    # Settings are shared with ChromIQ (same QSettings scope + preset store),
    # deliberately: charts and presets designed here appear in ChromIQ and
    # vice versa, and an already-configured Argyll path / language / theme
    # carries over. Without ChromIQ installed you simply start fresh.
    settings = AppSettings()

    from core.i18n import install_qt_translator, set_language
    set_language(settings.get("language", "en"))
    install_qt_translator(app)

    appearance = settings.get("appearance", "auto")
    apply_appearance(app, None, appearance)

    icon_path = resource_path("assets/app_icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # The editor drives ArgyllCMS printtarg ONLY to re-render charts that were
    # originally laid out by printtarg; everything the app creates itself uses
    # the built-in layout engine, so Argyll is an optional dependency here.
    runner = ArgyllRunner(settings)

    dlg = Ti2RelayoutDialog(runner, settings)
    apply_appearance(app, dlg, settings.get("appearance", "auto"))

    # As ChromIQ's tool it runs as a modal-ish QDialog; as THE app window it
    # must behave like a normal window — minimizable on macOS, maximizable on
    # Windows/Linux. Must be set before show().
    from PyQt6.QtCore import Qt as _Qt
    dlg.setWindowFlags(dlg.windowFlags()
                       | _Qt.WindowType.WindowMinimizeButtonHint
                       | _Qt.WindowType.WindowMaximizeButtonHint)

    # Standalone wording: there is no Create Chart tab to "apply" to — the
    # footer button saves the chart folder / exports the hand-off files.
    from core.i18n import tr as _tr
    if hasattr(dlg, "_apply_btn"):
        dlg._apply_btn.setText(_tr("Save / Export…").replace("&", "&&"))

    # In-app attribution, appended below the editor's own footer. The vendored
    # dialog stays byte-identical to ChromIQ's (tools/sync_from_chromiq.py), so
    # standalone-only chrome like this lives here in main.py. Helper-text
    # colour is theme-aware — must stay legible in BOTH light and dark mode.
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel
    from ui.theme import resolve_mode

    credit = QLabel(
        "Based on an original idea by Knut Georg Larsson — "
        "developed together with itsab1989", dlg)
    credit.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    credit.setToolTip(
        "ChromIQ Patches grew out of Knut Georg Larsson's idea for a patch "
        "generator that doesn't depend on ArgyllCMS targen. Knut and "
        "itsab1989 designed it together; itsab1989 wrote the code with "
        "Claude. The chart engine is shared with ChromIQ "
        "(github.com/itsab1989/ChromIQ).")

    def _style_credit() -> None:
        col = "#b8b8b8" if resolve_mode(settings.get("appearance", "auto")) == "dark" else "#4a4a4a"
        credit.setStyleSheet(f"color: {col}; font-size: 11px; padding-top: 2px;")

    _style_credit()
    dlg.layout().addWidget(credit)

    def _on_system_color_scheme_changed(_scheme=None) -> None:
        if settings.get("appearance", "auto") == "auto":
            apply_appearance(app, dlg, "auto")
        _style_credit()

    app.styleHints().colorSchemeChanged.connect(_on_system_color_scheme_changed)

    dlg.show()

    # Pay QtWebEngine's costly first-init at idle on the main loop, so the
    # on-demand 3D-cube preview never spins Chromium up mid-transition.
    from PyQt6.QtCore import QTimer
    from core.webengine_warmup import warm_up_webengine
    QTimer.singleShot(0, warm_up_webengine)

    log.info("Event loop starting")
    return app.exec()


def _hard_exit(code: int) -> None:
    """Flush our own buffers and hand straight to the OS, skipping CPython
    finalization — once any QWebEngineView has existed, letting the interpreter
    finalize walks SIP's wrapper graph into freed Chromium state and crashes
    (ChromIQ issue #38). All real cleanup already ran while the event loop was
    alive; there are no atexit hooks of our own to lose."""
    try:
        logging.shutdown()
    except Exception:
        pass
    try:
        if _crash_log is not None:
            _crash_log.flush()
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    os._exit(code)


if __name__ == "__main__":
    _hard_exit(main())
