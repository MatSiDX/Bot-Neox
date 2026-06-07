import os
import secrets
from datetime import datetime

from repositories.balance_repository import DATA_DIR
from utils.json_store import mutate_json, read_json


REPORT_DASHBOARD_FILE = os.path.join(DATA_DIR, "report_dashboard_requests.json")


class ReportDashboardRepository:
    def load(self):
        data = read_json(REPORT_DASHBOARD_FILE, {})
        return data if isinstance(data, dict) else {}

    def create(self, payload):
        request_id = secrets.token_urlsafe(12)
        request = {
            "id": request_id,
            "status": "pending",
            "payload": payload,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "error": "",
        }

        def mutate(data):
            data[request_id] = request
            return data

        mutate_json(REPORT_DASHBOARD_FILE, {}, mutate)
        return request

    def get(self, request_id):
        request = self.load().get(str(request_id))
        return dict(request) if isinstance(request, dict) else None

    def pending(self):
        return [
            dict(request)
            for request in self.load().values()
            if isinstance(request, dict) and request.get("status") == "pending"
        ]

    def mark(self, request_id, status, error=""):
        def mutate(data):
            request = data.get(str(request_id))
            if isinstance(request, dict):
                request["status"] = str(status)
                request["error"] = str(error or "")[:500]
                request["updated_at"] = datetime.now().isoformat()
            return data

        mutate_json(REPORT_DASHBOARD_FILE, {}, mutate)
