import json
import logging
import logging.handlers
import os
import typing

# Attributes every LogRecord carries by default - anything else on a record came from a
# call site's `extra={...}`, and that's what the audit trail actually cares about. "asctime"
# isn't part of a fresh record, but the console handler's Formatter.format() sets it as a
# side effect on the record itself (both handlers process the same instance), so it has to be
# excluded explicitly or it leaks into the JSON output whenever the console handler runs first.
_STANDARD_RECORD_ATTRS = set(logging.LogRecord(
    "", 0, "", 0, "", (), None
).__dict__.keys()) | {"asctime"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line: timestamp, source process, level, logger, message, plus
    whatever structured fields the call site passed via `extra=`. Meant for the audit log
    file, not the console - grep/jq-able, not meant to be read directly while running."""

    def __init__(self, *, source: str):
        super().__init__()
        self._source = source

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "source": self._source,
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


def configure_logging(*, source: str, log_dir: str, console: bool = True) -> None:
    """A rotating JSON-lines file is the audit trail for this process, tagged with `source`
    so server and client logs can be told apart once they're both being read.
    `console=False` keeps a process's logs out of its own stdout entirely - the client uses
    this so log lines never land in the middle of the chat view; the server keeps its console
    handler since that terminal isn't shared with anything else."""
    os.makedirs(log_dir, exist_ok=True)

    handlers: typing.List[logging.Handler] = []
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter(f'%(asctime)s - [{source}] - %(name)s - %(levelname)s - %(message)s')
        )
        handlers.append(console_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, f"{source}.log"), maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter(source=source))
    handlers.append(file_handler)

    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True)
