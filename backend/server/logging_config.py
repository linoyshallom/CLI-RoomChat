import json
import logging
import logging.handlers
import os

# Attributes every LogRecord carries by default - anything else on a record came from a
# call site's `extra={...}`, and that's what the audit trail actually cares about. "asctime"
# isn't part of a fresh record, but the console handler's Formatter.format() sets it as a
# side effect on the record itself (both handlers process the same instance), so it has to be
# excluded explicitly or it leaks into the JSON output whenever the console handler runs first.
_STANDARD_RECORD_ATTRS = set(logging.LogRecord(
    "", 0, "", 0, "", (), None
).__dict__.keys()) | {"asctime"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line: timestamp, level, logger, message, plus whatever structured
    fields the call site passed via `extra=`. Meant for the audit log file, not the console -
    grep/jq-able, not meant to be read directly while the server is running."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_fields = {
            key: value for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_ATTRS
        }
        payload.update(extra_fields)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(log_dir: str = None) -> None:
    """Console keeps the human-readable format for interactive use; a rotating JSON-lines file
    alongside it is the actual audit trail, since console output doesn't survive a restart."""
    log_dir = log_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "audit.log"), maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter())

    logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])
