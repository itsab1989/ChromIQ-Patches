"""Startup "update available" popup.

Replaces the old tab status-bar notice. Uses the shared tab-style masthead
(uppercase eyebrow + serif title over the five-colour spectrum stripe), the same
look as the Tools windows, via :func:`ui.tab_header.dialog_masthead`.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout,
)

from core.i18n import tr
from core.updater import _RELEASES_PAGE
from core.version import APP_VERSION
from ui.tab_header import dialog_masthead


class UpdateAvailableDialog(QDialog):
    """Tells the user a newer ChromIQ release exists and offers to download it.

    Read :attr:`disable_notifications` after :meth:`exec` to learn whether the
    user asked not to be reminded about new versions at all.
    """

    def __init__(self, latest: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Update available"))
        self.setMinimumWidth(540)
        self._latest = latest

        # Full-width masthead (stripe bleeds to the edges); content re-inset.
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        head, _header, stripe = dialog_masthead(
            self, tr("SOFTWARE UPDATE"), tr("Update available"))
        root.addLayout(head)
        root.addWidget(stripe)

        inner = QVBoxLayout()
        inner.setContentsMargins(22, 14, 22, 16)
        inner.setSpacing(12)
        root.addLayout(inner)

        body = QLabel(
            tr("ChromIQ {latest} is available — you're running {current}.\n\n"
               "Download the new version and install it over your current one; "
               "your settings and projects are kept.").format(
                   latest=latest, current=f"v{APP_VERSION}"),
            self)
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.PlainText)
        inner.addWidget(body)

        self._skip = QCheckBox(
            tr("Don't remind me of new available versions"), self)
        inner.addWidget(self._skip)

        bb = QDialogButtonBox(self)
        download_btn = bb.addButton(
            tr("Download"), QDialogButtonBox.ButtonRole.AcceptRole)
        later_btn = bb.addButton(
            tr("Later"), QDialogButtonBox.ButtonRole.RejectRole)
        download_btn.setDefault(True)
        download_btn.clicked.connect(self._open_download_page)
        later_btn.clicked.connect(self.reject)
        inner.addWidget(bb)

    def _open_download_page(self) -> None:
        QDesktopServices.openUrl(QUrl(_RELEASES_PAGE))
        self.accept()

    @property
    def disable_notifications(self) -> bool:
        return self._skip.isChecked()
