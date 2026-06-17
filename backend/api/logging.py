"""logging configuration for nokodo ai backend.

uses python's native logging module with custom formatting.
no external dependencies - future-proof and opentelemetry compatible.

features:
- colored console output for dev, json for production
- request_id context via contextvars (set by middleware)
- stdout only (12-factor app compliant)
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from api.boot_settings import boot_settings


# context variable for request-scoped data
# set by middleware, automatically included in all logs during that request
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


# ansi color codes
class Colors:
	"""ansi escape codes for terminal colors."""

	RESET = "\033[0m"
	BOLD = "\033[1m"
	DIM = "\033[2m"

	# log level colors
	DEBUG = "\033[36m"  # cyan
	INFO = "\033[32m"  # green
	WARNING = "\033[33m"  # yellow
	ERROR = "\033[31m"  # red
	CRITICAL = "\033[35;1m"  # magenta bold


LEVEL_COLORS = {
	"DEBUG": Colors.DEBUG,
	"INFO": Colors.INFO,
	"WARNING": Colors.WARNING,
	"ERROR": Colors.ERROR,
	"CRITICAL": Colors.CRITICAL,
}


NOISY_THIRD_PARTY_LOGGERS = (
	"httpcore",
	"httpx",
	"watchfiles",
	"openai",
	"grpc",
	"qdrant_client",
	"voyageai",
)


class ConsoleFormatter(logging.Formatter):
	"""
	human-readable colored formatter for development.

	format: [timestamp] [level] [logger] message | key=value key=value
	"""

	def format(self, record: logging.LogRecord) -> str:
		# timestamp
		ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

		# level with color
		level = record.levelname.lower()
		color = LEVEL_COLORS.get(record.levelname, Colors.RESET)
		level_str = f"{color}{level:<8}{Colors.RESET}"

		# logger name (shortened for readability)
		logger_name = self._shorten_name(record.name)

		# request id from context (if set)
		req_id = request_id_ctx.get()

		# message
		message = record.getMessage()

		# extra fields
		extras = self._get_extras(record)
		extras_str = self._format_extras(extras)

		# build log line with brackets
		parts = [f"[{ts}]", f"[{level_str}]", f"[{logger_name}]"]

		if req_id:
			parts.append(
				f"[{Colors.DIM}{self._short_request_id(req_id)}{Colors.RESET}]"
			)

		parts.append(message)

		if extras_str:
			parts.append(f"{Colors.DIM} [{extras_str}]{Colors.RESET}")

		result = " ".join(parts)

		# handle exceptions
		if record.exc_info and not record.exc_text:
			record.exc_text = self.formatException(record.exc_info)
		if record.exc_text:
			result = f"{result}\n{record.exc_text}"

		return result

	def _short_request_id(self, request_id: str) -> str:
		"""Return a compact request id string for console logs.

		TypeIDs (e.g. req_...) are time-ordered, so their leading characters can look
		stable across many requests. Showing the tail avoids the false impression
		that every request shares the same id.
		"""
		if "_" in request_id:
			request_id = request_id.rsplit("_", 1)[-1]
		if len(request_id) <= 8:
			return request_id
		return request_id[-8:]

	def _shorten_name(self, name: str) -> str:
		"""shorten logger name: api.v1.routers.users -> a.v.r.users"""
		parts = name.split(".")
		if len(parts) <= 2:
			return name
		abbreviated = [p[0] if p else "" for p in parts[:-1]]
		return ".".join([*abbreviated, parts[-1]])

	def _get_extras(self, record: logging.LogRecord) -> dict[str, Any]:
		"""extract extra fields from log record."""
		standard = {
			"name",
			"msg",
			"args",
			"created",
			"filename",
			"funcName",
			"levelname",
			"levelno",
			"lineno",
			"module",
			"msecs",
			"pathname",
			"process",
			"processName",
			"relativeCreated",
			"stack_info",
			"exc_info",
			"exc_text",
			"thread",
			"threadName",
			"taskName",
			"message",
		}
		return {k: v for k, v in record.__dict__.items() if k not in standard}

	def _format_extras(self, extras: dict[str, Any]) -> str:
		"""format extras as key=value pairs."""
		parts = []
		for k, v in extras.items():
			if isinstance(v, str) and " " in v:
				parts.append(f'{k}="{v}"')
			else:
				parts.append(f"{k}={v}")
		return " ".join(parts)


class JSONFormatter(logging.Formatter):
	"""
	json formatter for production environments.

	outputs one json object per line for log aggregators (elk, loki, etc).
	"""

	def format(self, record: logging.LogRecord) -> str:
		data: dict[str, Any] = {
			"ts": datetime.now(UTC).isoformat(),
			"level": record.levelname.lower(),
			"logger": record.name,
			"msg": record.getMessage(),
		}

		# add request_id from context
		req_id = request_id_ctx.get()
		if req_id:
			data["request_id"] = req_id

		# add extra fields
		extras = self._get_extras(record)
		if extras:
			data.update(extras)

		# add exception info
		if record.exc_info:
			data["exception"] = self.formatException(record.exc_info)

		# add thread info (useful for debugging thread pool usage)
		if record.thread:
			data["thread"] = record.thread

		return json.dumps(data, default=str, ensure_ascii=False)

	def _get_extras(self, record: logging.LogRecord) -> dict[str, Any]:
		"""extract extra fields from log record."""
		standard = {
			"name",
			"msg",
			"args",
			"created",
			"filename",
			"funcName",
			"levelname",
			"levelno",
			"lineno",
			"module",
			"msecs",
			"pathname",
			"process",
			"processName",
			"relativeCreated",
			"stack_info",
			"exc_info",
			"exc_text",
			"thread",
			"threadName",
			"taskName",
			"message",
		}
		return {k: v for k, v in record.__dict__.items() if k not in standard}


def get_log_level() -> int:
	"""determine log level based on settings."""
	if boot_settings.DEBUG:
		return logging.DEBUG
	if boot_settings.ENV == "dev":
		return logging.DEBUG
	return logging.INFO


def get_noisy_third_party_log_level(level: int) -> int:
	"""keep chatty sdk debug logs quiet unless logging is set below debug."""
	if level < logging.DEBUG:
		return logging.NOTSET
	return logging.WARNING


def configure_logging(
	level: int | None = None,
	json_logs: bool | None = None,
) -> None:
	"""
	configure logging for the application.

	call this once at startup, before any logging happens.

	args:
		level: log level override (default: auto from ENV)
		json_logs: force json format (default: settings.JSON_LOGS)
	"""
	if level is None:
		level = get_log_level()

	if json_logs is None:
		json_logs = boot_settings.JSON_LOGS

	# select formatter
	formatter: logging.Formatter
	if json_logs:
		formatter = JSONFormatter()
	else:
		formatter = ConsoleFormatter()

	# configure root logger
	root = logging.getLogger()
	root.setLevel(level)

	# clear existing handlers
	for h in root.handlers[:]:
		root.removeHandler(h)

	# stdout handler
	handler = logging.StreamHandler(sys.stdout)
	handler.setFormatter(formatter)
	handler.setLevel(level)
	root.addHandler(handler)

	# redirect uvicorn logs through our formatter
	for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
		uvi = logging.getLogger(name)
		uvi.handlers = []
		uvi.propagate = True

	# sqlalchemy - only warnings unless DEBUG
	sa = logging.getLogger("sqlalchemy.engine")
	sa.setLevel(logging.INFO if boot_settings.DEBUG else logging.WARNING)

	# suppress noisy third-party loggers
	noisy_logger_level = get_noisy_third_party_log_level(level)
	for name in NOISY_THIRD_PARTY_LOGGERS:
		logging.getLogger(name).setLevel(noisy_logger_level)


def get_logger(name: str) -> logging.Logger:
	"""
	get a logger instance.

	usage:
		from api.logging import get_logger
		logger = get_logger(__name__)
		logger.info("something happened", extra={"user_id": 123})
	"""
	return logging.getLogger(name)
