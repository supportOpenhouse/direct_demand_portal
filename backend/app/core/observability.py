"""Logging setup (human or JSON) + a per-request id carried via a ContextVar so
every log line in a request is correlated."""
import json
import logging
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(json_logs: bool) -> None:
    """Install a single stdout handler — JSON when json_logs else the human format."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter() if json_logs
        else logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
