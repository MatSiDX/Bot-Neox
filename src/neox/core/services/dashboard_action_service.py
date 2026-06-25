from __future__ import annotations

import secrets

from src.neox.core.repositories.dashboard_action_request_repository import DashboardActionRequestRepository


STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_RETRY = "retry"


class DashboardActionService:
    def __init__(self):
        self.repo = DashboardActionRequestRepository()

    def create_request(
        self,
        *,
        guild_id,
        action_type,
        payload,
        requested_by="",
        max_retries=3,
        idempotency_key=None,
        correlation_id=None,
    ):
        if idempotency_key:
            existing = self.repo.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        return self.repo.create(
            guild_id=guild_id,
            action_type=action_type,
            payload=payload,
            requested_by=requested_by,
            max_retries=max_retries,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id or secrets.token_urlsafe(10),
        )

    def get_request(self, request_id):
        return self.repo.get(request_id)

    def list_requests(self, *, statuses=None, action_types=None, limit=100):
        return self.repo.list_requests(
            statuses=statuses,
            action_types=action_types,
            limit=limit,
        )

    def claim_next_request(self, worker_id, *, action_types=None):
        return self.repo.claim_next(worker_id, action_types=action_types)

    def complete_request(self, request_id, *, result=None):
        return self.repo.mark_completed(request_id, result=result)

    def fail_request(self, request_id, *, error, result=None, retryable=False, retry_delay_seconds=30):
        current = self.repo.get(request_id)
        if not current:
            return None

        next_retry_count = int(current.get("retry_count") or 0) + 1
        max_retries = int(current.get("max_retries") or 0)
        if retryable and next_retry_count < max_retries:
            return self.repo.mark_retry(
                request_id,
                error=error,
                result=result,
                retry_delay_seconds=retry_delay_seconds,
            )

        return self.repo.mark_failed(
            request_id,
            error=error,
            result=result,
        )
