"""Debounced asynchronous JSON settings save controller.

Used by GUI event handlers that may be triggered repeatedly (for example channel
checkbox toggles).  It coalesces rapid edits and writes the latest payload on a
background QRunnable so slow disks / cloud-sync folders do not block the Qt main
thread.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

import config


class _SaveSignals(QObject):
    success = pyqtSignal(str, object)
    failure = pyqtSignal(str, str, object)


class _JsonSaveTask(QRunnable):
    def __init__(self, file_path: Path, payload: Dict[str, Any], token: int):
        super().__init__()
        self.file_path = Path(file_path)
        self.payload = copy.deepcopy(payload)
        self.token = token
        self.signals = _SaveSignals()

    def run(self):
        try:
            ok = config.save_json_file(self.file_path, self.payload)
            if ok:
                self.signals.success.emit(str(self.file_path), self.token)
            else:
                self.signals.failure.emit(str(self.file_path), "config.save_json_file returned False", self.token)
        except Exception as exc:
            self.signals.failure.emit(str(self.file_path), str(exc), self.token)


class JsonDebouncedSaveController(QObject):
    """Coalesce and asynchronously save JSON files from GUI code."""

    saveSucceeded = pyqtSignal(str, object)
    saveFailed = pyqtSignal(str, str, object)

    def __init__(self, parent=None, debounce_ms: int = 500):
        super().__init__(parent)
        self._debounce_ms = int(debounce_ms)
        self._pending_payloads: Dict[str, Dict[str, Any]] = {}
        self._tokens: Dict[str, int] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._flush_pending)
        self._pool = QThreadPool.globalInstance()

    def request_save(self, file_path: Path, payload: Dict[str, Any]) -> int:
        key = str(Path(file_path))
        token = self._tokens.get(key, 0) + 1
        self._tokens[key] = token
        self._pending_payloads[key] = copy.deepcopy(payload)
        self._timer.start(self._debounce_ms)
        return token

    def pending_payload(self, file_path: Path) -> Optional[Dict[str, Any]]:
        payload = self._pending_payloads.get(str(Path(file_path)))
        return copy.deepcopy(payload) if payload is not None else None

    def _flush_pending(self):
        pending = dict(self._pending_payloads)
        self._pending_payloads.clear()
        for key, payload in pending.items():
            token = self._tokens.get(key, 0)
            task = _JsonSaveTask(Path(key), payload, token)
            task.signals.success.connect(self._on_task_success)
            task.signals.failure.connect(self._on_task_failure)
            self._pool.start(task)

    def _on_task_success(self, file_path: str, token: object):
        self.saveSucceeded.emit(file_path, token)

    def _on_task_failure(self, file_path: str, error: str, token: object):
        self.saveFailed.emit(file_path, error, token)
