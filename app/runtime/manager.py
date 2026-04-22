from __future__ import annotations

from typing import Iterable

from PyQt6.QtCore import QObject, pyqtSignal

from app.db import DatabaseManager
from app.models import ProxyEntry, ProxyType, utc_now_iso
from app.runtime.contracts import EngineAdapter, RuntimeRouteController
from app.runtime.enums import (
    RouteOwnerKind,
    RuntimeEngineKind,
    RuntimeState,
    SessionStopReason,
    SystemProxyState,
)
from app.runtime.models import (
    LaunchSpec,
    RunningSession,
    RuntimeHumanStatus,
    RuntimePrefs,
    RuntimeSnapshot,
    SessionHistoryRecord,
    new_session_id,
)


ERROR_ENTRY_NOT_FOUND = "runtime.error.entry_not_found"
ERROR_ADAPTER_NOT_FOUND = "runtime.error.adapter_not_found"
ERROR_UNSUPPORTED_ENTRY = "runtime.error.unsupported_entry_type"
ERROR_PREPARE_FAILED = "runtime.error.launch_prepare_failed"
ERROR_START_FAILED = "runtime.error.launch_start_failed"
ERROR_STOP_FAILED = "runtime.error.stop_failed"
ERROR_POLL_FAILED = "runtime.error.poll_failed"
ERROR_SYSTEM_PROXY_APPLY_FAILED = "runtime.error.system_proxy_apply_failed"
ERROR_PRIMARY_SESSION_REQUIRED = "runtime.error.primary_requires_running_session"

WIREGUARD_ENGINES = {
    RuntimeEngineKind.WIREGUARD_WINDOWS,
    RuntimeEngineKind.WIREGUARD_MACOS,
    RuntimeEngineKind.AMNEZIAWG_WINDOWS,
    RuntimeEngineKind.AMNEZIAWG_MACOS,
}

AMNEZIAWG_ENGINES = {
    RuntimeEngineKind.AMNEZIAWG_WINDOWS,
    RuntimeEngineKind.AMNEZIAWG_MACOS,
}


class _NoopRouteController:
    def apply_primary_proxy(self, session: RunningSession) -> SystemProxyState:
        return SystemProxyState.APPLIED

    def clear_system_proxy(self, *, reason: SessionStopReason) -> SystemProxyState:
        return SystemProxyState.CLEAR

    def shutdown(self) -> SystemProxyState | None:
        return SystemProxyState.CLEAR


class RuntimeManager(QObject):
    snapshotChanged = pyqtSignal(object)
    sessionUpdated = pyqtSignal(str, object)
    sessionLogUpdated = pyqtSignal(str, str)
    humanStatusUpdated = pyqtSignal(str, object)
    operationFailed = pyqtSignal(str, str)

    def __init__(
        self,
        db: DatabaseManager,
        *,
        adapters: Iterable[EngineAdapter] | None = None,
        route_controller: RuntimeRouteController | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self._route_controller = route_controller or _NoopRouteController()
        self._adapters: list[EngineAdapter] = list(adapters or [])
        self._sessions_by_id: dict[str, RunningSession] = {}
        self._session_id_by_entry_id: dict[str, str] = {}
        self._adapter_by_session_id: dict[str, EngineAdapter] = {}
        self._launch_spec_by_session_id: dict[str, LaunchSpec] = {}
        self._primary_session_id = ""
        self._wireguard_session_id = ""
        self._route_owner_kind = RouteOwnerKind.NONE
        self._system_proxy_state = SystemProxyState.CLEAR
        self._system_proxy_entry_id = ""
        self._clear_system_proxy_on_app_exit = True

    def register_adapter(self, adapter: EngineAdapter) -> None:
        self._adapters.append(adapter)

    def adapters_snapshot(self) -> tuple[EngineAdapter, ...]:
        return tuple(self._adapters)

    def start_entry(self, entry_id: str, *, make_primary: bool = False) -> None:
        existing = self._session_for_entry(entry_id)
        if existing is not None:
            if make_primary:
                self.make_primary(entry_id)
            return

        entry = self.db.get_entry(entry_id, include_uri=not self.db.is_locked)
        if entry is None:
            self._emit_failure(entry_id, ERROR_ENTRY_NOT_FOUND)
            return

        prefs = self.db.load_runtime_prefs(entry_id)
        adapter, failure_reason = self._resolve_adapter(entry)
        if adapter is None:
            self._record_operation_failure(
                entry=entry,
                prefs=prefs,
                engine_kind=RuntimeEngineKind.UNSUPPORTED,
                failure_reason=failure_reason,
            )
            return

        desired_primary = bool(make_primary)
        technical_error = ""
        try:
            launch_spec = adapter.prepare_launch(entry, prefs, make_primary=desired_primary)
        except Exception as exc:
            failure_reason = self._exception_failure_reason(exc, ERROR_PREPARE_FAILED)
            technical_error = self._exception_last_error(exc)
            self._record_operation_failure(
                entry=entry,
                prefs=prefs,
                engine_kind=adapter.engine_kind,
                failure_reason=failure_reason,
                technical_error=technical_error,
                log_excerpt=self._exception_log_excerpt(exc),
            )
            return

        try:
            session = adapter.start(launch_spec)
        except Exception as exc:
            failure_reason = self._exception_failure_reason(exc, ERROR_START_FAILED)
            technical_error = self._exception_last_error(exc)
            self._record_operation_failure(
                entry=entry,
                prefs=prefs,
                engine_kind=adapter.engine_kind,
                failure_reason=failure_reason,
                technical_error=technical_error,
                log_excerpt=self._exception_log_excerpt(exc),
                session_id=launch_spec.session_id,
                log_path=launch_spec.log_path,
            )
            return

        session = self._normalize_started_session(entry, launch_spec, session)
        session.log_excerpt = self._safe_log_excerpt(adapter, session, session.log_excerpt)
        if session.is_terminal:
            if not session.failure_reason:
                session.failure_reason = ERROR_START_FAILED
            if technical_error and not session.last_error:
                session.last_error = technical_error
            self._persist_session_terminal_state(session, self._terminal_reason(session), log_path=launch_spec.log_path)
            self._emit_failure(session.entry_id, session.failure_reason)
            return

        prefs.last_used_at = session.started_at or utc_now_iso()
        prefs.last_error = ""
        prefs.auto_launch = True
        prefs.preferred_primary = bool(session.is_primary and not self._is_wireguard_session(session))
        self.db.save_runtime_prefs(prefs)
        if prefs.preferred_primary:
            self._clear_other_primary_preferences(session.entry_id)
        self._store_session(session, adapter, launch_spec)

        if self._is_wireguard_session(session):
            self._activate_wireguard(session)
        elif session.is_primary:
            self._promote_primary_session(session)

        self._emit_session_state(session)
        self._emit_snapshot()

    def stop_entry(self, entry_id: str) -> None:
        session = self._session_for_entry(entry_id)
        if session is None:
            return
        adapter = self._adapter_by_session_id.get(session.session_id)
        if adapter is None:
            self._finalize_terminal_session(session, SessionStopReason.USER_REQUEST)
            return
        try:
            updated_session = adapter.stop(session, reason=SessionStopReason.USER_REQUEST)
        except Exception as exc:
            updated_session = self._clone_session(session)
            updated_session.runtime_state = RuntimeState.ERROR
            updated_session.stopped_at = utc_now_iso()
            updated_session.failure_reason = self._exception_failure_reason(exc, ERROR_STOP_FAILED)
            updated_session.last_error = self._exception_last_error(exc)
            updated_session.log_excerpt = self._exception_log_excerpt(exc, updated_session.log_excerpt)
            updated_session.exit_code = self._exception_exit_code(exc, updated_session.exit_code)
        updated_session = self._merge_session_update(session, updated_session)
        updated_session.log_excerpt = self._safe_log_excerpt(adapter, updated_session, updated_session.log_excerpt)
        if updated_session.is_terminal:
            self._finalize_terminal_session(updated_session, SessionStopReason.USER_REQUEST)
            return
        self._store_session(updated_session, adapter, self._launch_spec_by_session_id.get(session.session_id))
        self._emit_session_state(updated_session)
        self._emit_snapshot()

    def stop_all(self) -> None:
        for session in list(self._sessions_by_id.values()):
            self._stop_session(session, SessionStopReason.USER_REQUEST)

    def make_primary(self, entry_id: str) -> None:
        session = self._session_for_entry(entry_id)
        if session is None:
            self._emit_failure(entry_id, ERROR_PRIMARY_SESSION_REQUIRED)
            return
        if self._is_wireguard_session(session):
            return
        session.is_primary = True
        self._promote_primary_session(session)
        self._emit_session_state(session)
        self._emit_snapshot()

    def poll_sessions(self) -> RuntimeSnapshot:
        for session in list(self._sessions_by_id.values()):
            adapter = self._adapter_by_session_id.get(session.session_id)
            if adapter is None:
                continue
            try:
                polled = adapter.poll(session)
            except Exception as exc:
                polled = self._clone_session(session)
                polled.runtime_state = RuntimeState.ERROR
                polled.stopped_at = utc_now_iso()
                polled.failure_reason = self._exception_failure_reason(exc, ERROR_POLL_FAILED)
                polled.last_error = self._exception_last_error(exc)
                polled.log_excerpt = self._exception_log_excerpt(exc, polled.log_excerpt)
                polled.exit_code = self._exception_exit_code(exc, polled.exit_code)
            updated_session = self._merge_session_update(session, polled)
            updated_session.log_excerpt = self._safe_log_excerpt(adapter, updated_session, updated_session.log_excerpt)
            if updated_session.is_terminal:
                self._finalize_terminal_session(updated_session, self._terminal_reason(updated_session))
                continue
            self._store_session(updated_session, adapter, self._launch_spec_by_session_id.get(session.session_id))
            if self._is_wireguard_session(updated_session):
                self._activate_wireguard(updated_session)
            elif updated_session.is_primary and not self._wireguard_session_id:
                self._promote_primary_session(updated_session)
            self._emit_session_state(updated_session)
        self._emit_snapshot()
        return self.snapshot()

    def snapshot(self) -> RuntimeSnapshot:
        sessions = [self._clone_session(session) for session in self._sessions_by_id.values()]
        sessions.sort(key=lambda item: (item.started_at, item.entry_name.lower(), item.session_id), reverse=True)
        return RuntimeSnapshot(
            sessions=sessions,
            primary_session_id=self._primary_session_id,
            route_owner_kind=self._route_owner_kind,
            system_proxy_state=self._system_proxy_state,
            system_proxy_entry_id=self._system_proxy_entry_id,
            wireguard_session_id=self._wireguard_session_id,
            updated_at=utc_now_iso(),
        )

    def history_for_entry(self, entry_id: str, limit: int = 50) -> list[SessionHistoryRecord]:
        return self.db.list_session_history(entry_id, limit=limit)

    def restore_sessions_on_launch(self) -> RuntimeSnapshot:
        settings = self.db.load_settings()
        if not settings.restore_sessions_on_launch:
            return self.snapshot()

        prefs_records = [prefs for prefs in self.db.list_runtime_prefs() if prefs.auto_launch]
        prefs_records.sort(key=lambda prefs: prefs.last_used_at, reverse=True)
        for prefs in prefs_records:
            self.start_entry(prefs.entry_id, make_primary=prefs.preferred_primary)
        return self.snapshot()

    def shutdown(self) -> None:
        settings = self.db.load_settings()
        self._clear_system_proxy_on_app_exit = settings.clear_system_proxy_on_exit
        for session in list(self._sessions_by_id.values()):
            self._stop_session(session, SessionStopReason.APP_EXIT)

        if settings.clear_system_proxy_on_exit:
            self._clear_system_proxy(SessionStopReason.APP_EXIT)

        shutdown_result = self._route_controller.shutdown()
        if settings.clear_system_proxy_on_exit and isinstance(shutdown_result, SystemProxyState):
            self._system_proxy_state = shutdown_result
        self._clear_system_proxy_on_app_exit = True
        self._emit_snapshot()

    def _stop_session(self, session: RunningSession, reason: SessionStopReason) -> None:
        adapter = self._adapter_by_session_id.get(session.session_id)
        if adapter is None:
            self._finalize_terminal_session(session, reason)
            return
        try:
            updated = adapter.stop(session, reason=reason)
        except Exception as exc:
            updated = self._clone_session(session)
            updated.runtime_state = RuntimeState.ERROR
            updated.stopped_at = utc_now_iso()
            updated.failure_reason = ERROR_STOP_FAILED
            updated.last_error = self._technical_error(exc)
        updated = self._merge_session_update(session, updated)
        updated.log_excerpt = self._safe_log_excerpt(adapter, updated, updated.log_excerpt)
        if updated.is_terminal:
            self._finalize_terminal_session(updated, reason)
            return
        self._store_session(updated, adapter, self._launch_spec_by_session_id.get(session.session_id))
        self._emit_session_state(updated)

    def _resolve_adapter(self, entry: ProxyEntry) -> tuple[EngineAdapter | None, str]:
        if entry.type == ProxyType.OTHER:
            return None, ERROR_UNSUPPORTED_ENTRY
        for adapter in self._adapters:
            try:
                if adapter.supports(entry):
                    return adapter, ""
            except Exception:
                continue
        return None, ERROR_ADAPTER_NOT_FOUND

    def _normalize_started_session(
        self,
        entry: ProxyEntry,
        launch_spec: LaunchSpec,
        session: RunningSession,
    ) -> RunningSession:
        normalized = self._clone_session(session)
        normalized.session_id = normalized.session_id or launch_spec.session_id
        normalized.entry_id = normalized.entry_id or entry.id
        normalized.entry_name = normalized.entry_name or entry.name or launch_spec.display_name or entry.server_host
        normalized.engine_kind = (
            normalized.engine_kind
            if normalized.engine_kind != RuntimeEngineKind.UNSUPPORTED
            else launch_spec.engine_kind
        )
        normalized.http_port = normalized.http_port if normalized.http_port is not None else launch_spec.http_port
        normalized.socks_port = normalized.socks_port if normalized.socks_port is not None else launch_spec.socks_port
        normalized.started_at = normalized.started_at or launch_spec.created_at or utc_now_iso()
        normalized.handle = normalized.handle or launch_spec.session_id
        normalized.is_primary = normalized.is_primary or launch_spec.resolved_primary
        normalized.metadata = {
            **dict(launch_spec.metadata),
            **dict(normalized.metadata),
        }
        if self._is_wireguard_engine(normalized.engine_kind):
            normalized.route_owner_kind = RouteOwnerKind.WIREGUARD
        elif normalized.is_primary and not self._wireguard_session_id:
            normalized.route_owner_kind = RouteOwnerKind.PROXY
        else:
            normalized.route_owner_kind = RouteOwnerKind.NONE
        return normalized

    def _merge_session_update(self, previous: RunningSession, updated: RunningSession) -> RunningSession:
        merged = self._clone_session(updated)
        merged.session_id = merged.session_id or previous.session_id
        merged.entry_id = merged.entry_id or previous.entry_id
        merged.entry_name = merged.entry_name or previous.entry_name
        merged.engine_kind = (
            merged.engine_kind if merged.engine_kind != RuntimeEngineKind.UNSUPPORTED else previous.engine_kind
        )
        merged.http_port = merged.http_port if merged.http_port is not None else previous.http_port
        merged.socks_port = merged.socks_port if merged.socks_port is not None else previous.socks_port
        merged.pid = merged.pid if merged.pid is not None else previous.pid
        merged.handle = merged.handle or previous.handle
        merged.started_at = merged.started_at or previous.started_at
        merged.is_primary = merged.is_primary or previous.is_primary or self._primary_session_id == previous.session_id
        merged.metadata = {
            **dict(previous.metadata),
            **dict(merged.metadata),
        }
        if not merged.stopped_at and merged.is_terminal:
            merged.stopped_at = utc_now_iso()
        if merged.route_owner_kind == RouteOwnerKind.NONE:
            if self._is_wireguard_session(merged):
                merged.route_owner_kind = RouteOwnerKind.WIREGUARD
            elif merged.is_primary and not self._wireguard_session_id:
                merged.route_owner_kind = RouteOwnerKind.PROXY
        return merged

    def _store_session(
        self,
        session: RunningSession,
        adapter: EngineAdapter,
        launch_spec: LaunchSpec | None,
    ) -> None:
        self._sessions_by_id[session.session_id] = session
        self._session_id_by_entry_id[session.entry_id] = session.session_id
        self._adapter_by_session_id[session.session_id] = adapter
        if launch_spec is not None:
            self._launch_spec_by_session_id[session.session_id] = launch_spec

    def _promote_primary_session(self, session: RunningSession) -> None:
        previous_primary = self._primary_session()
        if previous_primary is not None and previous_primary.session_id != session.session_id:
            previous_primary.is_primary = False
            previous_primary.route_owner_kind = RouteOwnerKind.NONE
            self._emit_session_state(previous_primary)

        self._primary_session_id = session.session_id
        session.is_primary = True
        self._set_primary_preference(session.entry_id)

        if self._wireguard_session_id:
            session.route_owner_kind = RouteOwnerKind.NONE
            self._route_owner_kind = RouteOwnerKind.WIREGUARD
            self._system_proxy_entry_id = ""
            if self._system_proxy_state != SystemProxyState.ERROR:
                self._system_proxy_state = SystemProxyState.CLEAR
            return

        if previous_primary is not None and previous_primary.session_id != session.session_id:
            self._clear_system_proxy(SessionStopReason.PRIMARY_SWITCH)

        try:
            state = self._route_controller.apply_primary_proxy(session)
        except Exception as exc:
            session.route_owner_kind = RouteOwnerKind.NONE
            session.failure_reason = ERROR_SYSTEM_PROXY_APPLY_FAILED
            session.last_error = self._technical_error(exc)
            self._system_proxy_state = SystemProxyState.ERROR
            self._system_proxy_entry_id = ""
            self._route_owner_kind = RouteOwnerKind.NONE
            self._update_runtime_prefs_error(session.entry_id, session.failure_reason)
            self._emit_failure(session.entry_id, session.failure_reason)
            return

        self._system_proxy_state = state
        self._system_proxy_entry_id = session.entry_id if state == SystemProxyState.APPLIED else ""
        self._route_owner_kind = RouteOwnerKind.PROXY if state == SystemProxyState.APPLIED else RouteOwnerKind.NONE
        session.route_owner_kind = RouteOwnerKind.PROXY if state == SystemProxyState.APPLIED else RouteOwnerKind.NONE
        if state == SystemProxyState.ERROR:
            session.failure_reason = ERROR_SYSTEM_PROXY_APPLY_FAILED
            self._update_runtime_prefs_error(session.entry_id, session.failure_reason)
            self._emit_failure(session.entry_id, session.failure_reason)

    def _activate_wireguard(self, session: RunningSession) -> None:
        current_wireguard = self._sessions_by_id.get(self._wireguard_session_id)
        if current_wireguard is not None and current_wireguard.session_id != session.session_id:
            self._stop_session(current_wireguard, SessionStopReason.PRIMARY_SWITCH)

        self._wireguard_session_id = session.session_id
        session.route_owner_kind = RouteOwnerKind.WIREGUARD
        self._route_owner_kind = RouteOwnerKind.WIREGUARD
        self._system_proxy_entry_id = ""
        self._system_proxy_state = self._clear_system_proxy(SessionStopReason.ROUTE_TAKEN_BY_WIREGUARD)

        primary_session = self._primary_session()
        if primary_session is not None and primary_session.session_id != session.session_id:
            primary_session.route_owner_kind = RouteOwnerKind.NONE
            self._emit_session_state(primary_session)

    def _finalize_terminal_session(self, session: RunningSession, reason: SessionStopReason) -> None:
        snapshot_session = self._clone_session(session)
        snapshot_session.is_primary = snapshot_session.is_primary or self._primary_session_id == snapshot_session.session_id
        if self._is_wireguard_session(snapshot_session):
            snapshot_session.route_owner_kind = RouteOwnerKind.WIREGUARD
        elif snapshot_session.is_primary and not self._wireguard_session_id:
            snapshot_session.route_owner_kind = RouteOwnerKind.PROXY

        was_primary = self._primary_session_id == session.session_id
        was_wireguard = self._wireguard_session_id == session.session_id or self._is_wireguard_session(session)

        if was_primary:
            self._primary_session_id = ""
            should_clear_proxy = (
                reason != SessionStopReason.APP_EXIT or self._clear_system_proxy_on_app_exit
            )
            if should_clear_proxy and (not self._wireguard_session_id or was_wireguard):
                self._clear_system_proxy(reason)

        if was_wireguard:
            self._wireguard_session_id = ""
            self._route_owner_kind = RouteOwnerKind.NONE
            self._system_proxy_entry_id = ""
            if self._system_proxy_state != SystemProxyState.ERROR:
                self._system_proxy_state = SystemProxyState.CLEAR
            primary_session = self._primary_session()
            if primary_session is not None:
                primary_session.route_owner_kind = RouteOwnerKind.NONE
                self._emit_session_state(primary_session)

        self._persist_session_terminal_state(snapshot_session, reason)
        self._drop_session(session.session_id)
        self._emit_session_state(snapshot_session)
        self._emit_snapshot()

    def _persist_session_terminal_state(
        self,
        session: RunningSession,
        reason: SessionStopReason,
        *,
        log_path: str = "",
    ) -> None:
        if not session.stopped_at:
            session.stopped_at = utc_now_iso()
        history_log_path = log_path
        if not history_log_path:
            launch_spec = self._launch_spec_by_session_id.get(session.session_id)
            history_log_path = getattr(launch_spec, "log_path", "") if launch_spec is not None else ""
        self.db.record_session_history(session.to_history_record(log_path=history_log_path))
        prefs = self.db.load_runtime_prefs(session.entry_id)
        prefs.last_used_at = session.stopped_at or utc_now_iso()
        prefs.last_error = session.failure_reason
        if reason == SessionStopReason.APP_EXIT:
            prefs.auto_launch = True
            prefs.preferred_primary = bool(session.is_primary and not self._is_wireguard_session(session))
            if prefs.preferred_primary:
                self._clear_other_primary_preferences(session.entry_id)
        else:
            prefs.auto_launch = False
            if session.is_primary or prefs.preferred_primary:
                prefs.preferred_primary = False
        self.db.save_runtime_prefs(prefs)

    def _record_operation_failure(
        self,
        *,
        entry: ProxyEntry,
        prefs: RuntimePrefs,
        engine_kind: RuntimeEngineKind,
        failure_reason: str,
        technical_error: str = "",
        log_excerpt: str = "",
        session_id: str | None = None,
        log_path: str = "",
    ) -> None:
        timestamp = utc_now_iso()
        prefs.last_used_at = timestamp
        prefs.last_error = failure_reason
        prefs.auto_launch = False
        prefs.preferred_primary = False
        self.db.save_runtime_prefs(prefs)
        record = SessionHistoryRecord(
            session_id=session_id or new_session_id(),
            entry_id=entry.id,
            entry_name=entry.name,
            engine_kind=engine_kind.value,
            state=RuntimeState.ERROR.value,
            primary_flag=False,
            route_owner_kind=RouteOwnerKind.NONE.value,
            started_at=timestamp,
            stopped_at=timestamp,
            failure_reason=failure_reason,
            short_log_excerpt=log_excerpt or technical_error,
            log_path=log_path,
        )
        self.db.record_session_history(record)
        self._emit_failure(entry.id, failure_reason)

    def _clear_system_proxy(self, reason: SessionStopReason) -> SystemProxyState:
        try:
            state = self._route_controller.clear_system_proxy(reason=reason)
        except Exception:
            state = SystemProxyState.ERROR
        self._system_proxy_state = state
        self._system_proxy_entry_id = ""
        if self._wireguard_session_id:
            self._route_owner_kind = RouteOwnerKind.WIREGUARD
        elif state != SystemProxyState.ERROR:
            self._route_owner_kind = RouteOwnerKind.NONE
        return state

    def _session_for_entry(self, entry_id: str) -> RunningSession | None:
        session_id = self._session_id_by_entry_id.get(entry_id)
        if not session_id:
            return None
        return self._sessions_by_id.get(session_id)

    def _primary_session(self) -> RunningSession | None:
        if not self._primary_session_id:
            return None
        return self._sessions_by_id.get(self._primary_session_id)

    def _drop_session(self, session_id: str) -> None:
        session = self._sessions_by_id.pop(session_id, None)
        if session is not None:
            self._session_id_by_entry_id.pop(session.entry_id, None)
        self._adapter_by_session_id.pop(session_id, None)
        self._launch_spec_by_session_id.pop(session_id, None)

    def _safe_log_excerpt(self, adapter: EngineAdapter, session: RunningSession, fallback: str = "") -> str:
        try:
            max_lines = max(int(self.db.load_settings().log_retention_lines), 1)
        except Exception:
            max_lines = 400
        try:
            return adapter.read_log_excerpt(session, max_lines=max_lines) or fallback
        except Exception:
            return fallback

    def _terminal_reason(self, session: RunningSession) -> SessionStopReason:
        if session.runtime_state == RuntimeState.ERROR:
            return SessionStopReason.ENGINE_CRASH
        if session.exit_code not in (None, 0):
            return SessionStopReason.ENGINE_CRASH
        return SessionStopReason.ENGINE_EXIT

    def _is_wireguard_engine(self, engine_kind: RuntimeEngineKind) -> bool:
        return engine_kind in WIREGUARD_ENGINES

    def _is_amneziawg_engine(self, engine_kind: RuntimeEngineKind) -> bool:
        return engine_kind in AMNEZIAWG_ENGINES

    def _is_wireguard_session(self, session: RunningSession) -> bool:
        return self._is_wireguard_engine(session.engine_kind) or session.route_owner_kind == RouteOwnerKind.WIREGUARD

    def _clone_session(self, session: RunningSession) -> RunningSession:
        return RunningSession.from_dict(session.to_dict())

    def _emit_failure(self, entry_id: str, failure_reason: str) -> None:
        self.operationFailed.emit(entry_id, failure_reason)

    def _emit_session_state(self, session: RunningSession) -> None:
        self.sessionUpdated.emit(session.session_id, self._clone_session(session))
        self.sessionLogUpdated.emit(session.session_id, session.log_excerpt)
        self.humanStatusUpdated.emit(session.session_id, self._build_human_status(session))

    def _emit_snapshot(self) -> None:
        self.snapshotChanged.emit(self.snapshot())

    def _build_human_status(self, session: RunningSession) -> RuntimeHumanStatus:
        params = {
            "entry_id": session.entry_id,
            "session_id": session.session_id,
        }
        if session.http_port is not None:
            params["http_port"] = str(session.http_port)
        if session.socks_port is not None:
            params["socks_port"] = str(session.socks_port)

        if session.runtime_state == RuntimeState.ERROR:
            return RuntimeHumanStatus(
                entry_id=session.entry_id,
                session_id=session.session_id,
                tone="danger",
                title_key="runtime.state.error",
                summary_key="runtime.summary.error",
                params=params,
            )
        if self._is_wireguard_session(session):
            title_key = (
                "runtime.state.amneziawg"
                if self._is_amneziawg_engine(session.engine_kind)
                else "runtime.state.wireguard"
            )
            summary_key = (
                "runtime.summary.route_owner_amneziawg"
                if self._is_amneziawg_engine(session.engine_kind)
                else "runtime.summary.route_owner_wireguard"
            )
            return RuntimeHumanStatus(
                entry_id=session.entry_id,
                session_id=session.session_id,
                tone="info",
                title_key=title_key,
                summary_key=summary_key,
                params=params,
            )
        if session.runtime_state == RuntimeState.STARTING:
            return RuntimeHumanStatus(
                entry_id=session.entry_id,
                session_id=session.session_id,
                tone="warning",
                title_key="runtime.state.starting",
                summary_key="runtime.summary.starting",
                params=params,
            )
        if session.runtime_state == RuntimeState.STOPPING:
            return RuntimeHumanStatus(
                entry_id=session.entry_id,
                session_id=session.session_id,
                tone="warning",
                title_key="runtime.state.stopping",
                summary_key="runtime.summary.stopping",
                params=params,
            )
        if session.is_primary:
            return RuntimeHumanStatus(
                entry_id=session.entry_id,
                session_id=session.session_id,
                tone="success",
                title_key="runtime.state.primary",
                summary_key="runtime.summary.primary_proxy",
                params=params,
            )
        if session.runtime_state == RuntimeState.RUNNING:
            return RuntimeHumanStatus(
                entry_id=session.entry_id,
                session_id=session.session_id,
                tone="success",
                title_key="runtime.state.running",
                summary_key="runtime.summary.running_local",
                params=params,
            )
        return RuntimeHumanStatus(
            entry_id=session.entry_id,
            session_id=session.session_id,
            tone="muted",
            title_key="runtime.state.disconnected",
            summary_key="runtime.summary.disconnected",
            params=params,
        )

    def _technical_error(self, exc: Exception) -> str:
        message = str(exc).strip()
        if not message:
            return exc.__class__.__name__
        return f"{exc.__class__.__name__}: {message}"

    def _exception_failure_reason(self, exc: Exception, default: str) -> str:
        failure_reason = getattr(exc, "failure_reason", "")
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            return default
        return failure_reason.strip()

    def _exception_last_error(self, exc: Exception) -> str:
        last_error = getattr(exc, "last_error", "")
        if isinstance(last_error, str) and last_error.strip():
            return last_error.strip()
        return self._technical_error(exc)

    def _exception_log_excerpt(self, exc: Exception, fallback: str = "") -> str:
        log_excerpt = getattr(exc, "log_excerpt", "")
        if isinstance(log_excerpt, str) and log_excerpt.strip():
            return log_excerpt.strip()
        return fallback

    def _exception_exit_code(self, exc: Exception, fallback: int | None = None) -> int | None:
        exit_code = getattr(exc, "exit_code", None)
        if isinstance(exit_code, int):
            return exit_code
        return fallback

    def _update_runtime_prefs_error(self, entry_id: str, failure_reason: str) -> None:
        prefs = self.db.load_runtime_prefs(entry_id)
        prefs.last_used_at = utc_now_iso()
        prefs.last_error = failure_reason
        self.db.save_runtime_prefs(prefs)

    def _set_primary_preference(self, entry_id: str) -> None:
        prefs = self.db.load_runtime_prefs(entry_id)
        prefs.auto_launch = True
        prefs.preferred_primary = True
        prefs.last_used_at = utc_now_iso()
        self.db.save_runtime_prefs(prefs)
        self._clear_other_primary_preferences(entry_id)

    def _clear_other_primary_preferences(self, entry_id: str) -> None:
        for prefs in self.db.list_runtime_prefs():
            if prefs.entry_id == entry_id or not prefs.preferred_primary:
                continue
            prefs.preferred_primary = False
            self.db.save_runtime_prefs(prefs)
