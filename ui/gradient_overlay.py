"""Gradient wash overlay — paints a colour-to-transparent strip at the top of a tab pane."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter
from PyQt6.QtWidgets import QWidget

_HEIGHT = 50  # px
_ALPHA  = 15  # ≈ 6 % opacity at the top


class GradientOverlay(QWidget):
    """Transparent overlay that draws a vertical gradient over the top 50 px.

    Passes all mouse/keyboard events through to siblings beneath it.
    Install one on each tab widget after the tab widget is fully built.
    """

    def __init__(self, color: str, parent: QWidget,
                 alpha: int = _ALPHA, height: int = _HEIGHT,
                 on_top: bool = True) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._alpha = alpha
        self._height = height
        # When True the wash is raised above the content (subtle tint over it,
        # as on the main-window tabs). When False it sits just above the parent's
        # background but below the content, so opaque widgets (e.g. the editor's
        # New chart / Load .ti2 / undo / redo buttons in the headline row) paint
        # over it while the transparent headline text still shows it behind.
        self._on_top = on_top
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        parent.installEventFilter(self)
        self._fit()
        self._restack()

    # ------------------------------------------------------------------

    def _restack(self) -> None:
        if self._on_top:
            self.raise_()
        else:
            self.lower()

    def _fit(self) -> None:
        p = self.parent()
        if p:
            self.setGeometry(0, 0, p.width(), self._height)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.parent():
            t = event.type()
            if t == QEvent.Type.Resize:
                self._fit()
                self._restack()
            elif t == QEvent.Type.Show:
                self._restack()
        return False

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        grad = QLinearGradient(0, 0, 0, self._height)
        r, g, b = self._color.red(), self._color.green(), self._color.blue()
        # Both stops use the same hue — avoids the black fringe from
        # pre-multiplied alpha interpolation toward QColor(0,0,0,0).
        n = 8
        for i in range(n + 1):
            t = i / n
            a = round(self._alpha * (1 - t) ** 2)
            grad.setColorAt(t, QColor(r, g, b, a))
        painter.fillRect(self.rect(), grad)
        painter.end()

    def showEvent(self, event) -> None:  # type: ignore[override]
        self._restack()
