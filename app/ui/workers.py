from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(object)
    progress = pyqtSignal(object)


class FunctionWorker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, progress_callback=self.signals.progress, **self.kwargs)
        except Exception as exc:  # pragma: no cover - exercised indirectly in UI tests
            self.signals.error.emit(exc)
        else:
            self.signals.finished.emit(result)
