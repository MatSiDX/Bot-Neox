import hashlib
import json

from services.dashboard_action_service import DashboardActionService


REPORT_DASHBOARD_ACTION_TYPE = "publish_report"


class ReportDashboardRepository:
    def __init__(self):
        self.service = DashboardActionService()

    def create(self, payload, *, requested_by="", idempotency_key=None):
        payload_fingerprint = hashlib.sha256(
            json.dumps(payload or {}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        idempotency_key = ":".join(
            [
                REPORT_DASHBOARD_ACTION_TYPE,
                str(payload.get("guild_id") or ""),
                str(payload.get("caller_id") or ""),
                str(payload.get("numero_ava") or ""),
                "send" if payload.get("send_to_channel", True) else "preview",
                str(idempotency_key or payload_fingerprint),
            ]
        )
        return self.service.create_request(
            guild_id=payload.get("guild_id"),
            action_type=REPORT_DASHBOARD_ACTION_TYPE,
            payload=payload,
            requested_by=requested_by or payload.get("caller_id") or "",
            max_retries=3,
            idempotency_key=idempotency_key,
        )

    def get(self, request_id):
        request = self.service.get_request(request_id)
        return self._to_legacy_shape(request)

    def pending(self):
        requests = self.service.list_requests(
            statuses=["pending", "retry"],
            action_types=[REPORT_DASHBOARD_ACTION_TYPE],
            limit=100,
        )
        return [self._to_legacy_shape(request) for request in requests]

    def mark(self, request_id, status, error=""):
        normalized = str(status or "").strip().lower()
        if normalized == "completed":
            return self._to_legacy_shape(self.service.complete_request(request_id))
        if normalized in {"error", "failed"}:
            return self._to_legacy_shape(
                self.service.fail_request(
                    request_id,
                    error=error,
                    retryable=False,
                )
            )
        return self.get(request_id)

    def _to_legacy_shape(self, request):
        if not request:
            return None

        status = str(request.get("status") or "pending")
        if status == "failed":
            status = "error"

        return {
            "id": request.get("id", ""),
            "status": status,
            "payload": request.get("payload") or {},
            "result": request.get("result"),
            "created_at": request.get("created_at", ""),
            "updated_at": request.get("updated_at", ""),
            "processed_at": request.get("processed_at", ""),
            "error": request.get("error", ""),
            "retry_count": request.get("retry_count", 0),
            "max_retries": request.get("max_retries", 0),
            "correlation_id": request.get("correlation_id", ""),
            "action_type": request.get("action_type", REPORT_DASHBOARD_ACTION_TYPE),
        }
