"""tests for the logging module."""

from __future__ import annotations

import json
import logging
import sys
from unittest.mock import patch

from api.logging import (
	NOISY_THIRD_PARTY_LOGGERS,
	Colors,
	ConsoleFormatter,
	JSONFormatter,
	configure_logging,
	get_log_level,
	get_logger,
	get_noisy_third_party_log_level,
	request_id_ctx,
)


class TestColors:
	"""tests for ansi color codes."""

	def test_colors_are_ansi_escape_sequences(self) -> None:
		assert Colors.RESET.startswith("\033[")
		assert Colors.DEBUG.startswith("\033[")
		assert Colors.INFO.startswith("\033[")
		assert Colors.WARNING.startswith("\033[")
		assert Colors.ERROR.startswith("\033[")
		assert Colors.CRITICAL.startswith("\033[")


class TestConsoleFormatter:
	"""tests for the console formatter."""

	def setup_method(self) -> None:
		self.formatter = ConsoleFormatter()
		self.logger = logging.getLogger("test.console.formatter")
		self.logger.setLevel(logging.DEBUG)

	def test_format_basic_message(self) -> None:
		record = self.logger.makeRecord(
			name="test.logger",
			level=logging.INFO,
			fn="test.py",
			lno=1,
			msg="hello world",
			args=(),
			exc_info=None,
		)
		output = self.formatter.format(record)

		assert "[test.logger]" in output
		assert "hello world" in output
		# level contains ansi codes, so check for the text part
		assert "info" in output

	def test_format_with_extras(self) -> None:
		record = self.logger.makeRecord(
			name="test.logger",
			level=logging.INFO,
			fn="test.py",
			lno=1,
			msg="with extras",
			args=(),
			exc_info=None,
		)
		record.user_id = 123
		record.action = "login"
		output = self.formatter.format(record)

		assert "user_id=123" in output
		assert "action=login" in output

	def test_format_extras_with_spaces_quoted(self) -> None:
		record = self.logger.makeRecord(
			name="test.logger",
			level=logging.INFO,
			fn="test.py",
			lno=1,
			msg="test",
			args=(),
			exc_info=None,
		)
		record.path = "/api/users list"
		output = self.formatter.format(record)

		assert 'path="/api/users list"' in output

	def test_format_with_request_id(self) -> None:
		token = request_id_ctx.set("abc12345-6789-0000")
		try:
			record = self.logger.makeRecord(
				name="test.logger",
				level=logging.INFO,
				fn="test.py",
				lno=1,
				msg="request log",
				args=(),
				exc_info=None,
			)
			output = self.formatter.format(record)

			# should show a shortened request id (may have ansi codes)
			assert "789-0000" in output
		finally:
			request_id_ctx.reset(token)

	def test_format_without_request_id(self) -> None:
		# ensure no request_id in context
		assert request_id_ctx.get() is None

		record = self.logger.makeRecord(
			name="test.logger",
			level=logging.INFO,
			fn="test.py",
			lno=1,
			msg="no request",
			args=(),
			exc_info=None,
		)
		output = self.formatter.format(record)

		# should not have a request_id bracket (only timestamp, level, logger)
		bracket_count = output.count("[")
		# timestamp, level, logger = 3 brackets minimum
		assert bracket_count >= 3

	def test_format_with_exception(self) -> None:
		try:
			raise ValueError("test error")
		except ValueError:
			exc_info = sys.exc_info()
			record = self.logger.makeRecord(
				name="test.logger",
				level=logging.ERROR,
				fn="test.py",
				lno=1,
				msg="error occurred",
				args=(),
				exc_info=exc_info,
			)
		output = self.formatter.format(record)

		assert "error occurred" in output
		assert "ValueError" in output
		assert "test error" in output

	def test_shorten_name_short_names_unchanged(self) -> None:
		assert self.formatter._shorten_name("api") == "api"
		assert self.formatter._shorten_name("api.main") == "api.main"

	def test_shorten_name_long_names_abbreviated(self) -> None:
		assert self.formatter._shorten_name("api.core.database") == "a.c.database"
		assert self.formatter._shorten_name("api.v1.routers.users") == "a.v.r.users"

	def test_shorten_name_empty_parts_handled(self) -> None:
		# edge case: empty parts in name
		assert self.formatter._shorten_name("api..database") == "a..database"

	def test_all_log_levels_formatted(self) -> None:
		levels = [
			(logging.DEBUG, "debug"),
			(logging.INFO, "info"),
			(logging.WARNING, "warning"),
			(logging.ERROR, "error"),
			(logging.CRITICAL, "critical"),
		]
		for level, name in levels:
			record = self.logger.makeRecord(
				name="test",
				level=level,
				fn="test.py",
				lno=1,
				msg=f"{name} message",
				args=(),
				exc_info=None,
			)
			output = self.formatter.format(record)
			assert name in output.lower()


class TestJSONFormatter:
	"""tests for the json formatter."""

	def setup_method(self) -> None:
		self.formatter = JSONFormatter()
		self.logger = logging.getLogger("test.json.formatter")
		self.logger.setLevel(logging.DEBUG)

	def test_format_produces_valid_json(self) -> None:
		record = self.logger.makeRecord(
			name="test.logger",
			level=logging.INFO,
			fn="test.py",
			lno=1,
			msg="json test",
			args=(),
			exc_info=None,
		)
		output = self.formatter.format(record)
		data = json.loads(output)

		assert data["level"] == "info"
		assert data["logger"] == "test.logger"
		assert data["msg"] == "json test"
		assert "ts" in data

	def test_format_with_extras(self) -> None:
		record = self.logger.makeRecord(
			name="test.logger",
			level=logging.INFO,
			fn="test.py",
			lno=1,
			msg="with extras",
			args=(),
			exc_info=None,
		)
		record.user_id = 456
		record.method = "POST"
		output = self.formatter.format(record)
		data = json.loads(output)

		assert data["user_id"] == 456
		assert data["method"] == "POST"

	def test_format_with_request_id(self) -> None:
		token = request_id_ctx.set("req-123-456-789")
		try:
			record = self.logger.makeRecord(
				name="test.logger",
				level=logging.INFO,
				fn="test.py",
				lno=1,
				msg="request log",
				args=(),
				exc_info=None,
			)
			output = self.formatter.format(record)
			data = json.loads(output)

			assert data["request_id"] == "req-123-456-789"
		finally:
			request_id_ctx.reset(token)

	def test_format_without_request_id(self) -> None:
		assert request_id_ctx.get() is None

		record = self.logger.makeRecord(
			name="test.logger",
			level=logging.INFO,
			fn="test.py",
			lno=1,
			msg="no request",
			args=(),
			exc_info=None,
		)
		output = self.formatter.format(record)
		data = json.loads(output)

		assert "request_id" not in data

	def test_format_with_exception(self) -> None:
		try:
			raise RuntimeError("json error test")
		except RuntimeError:
			exc_info = sys.exc_info()
			record = self.logger.makeRecord(
				name="test.logger",
				level=logging.ERROR,
				fn="test.py",
				lno=1,
				msg="error",
				args=(),
				exc_info=exc_info,
			)
		output = self.formatter.format(record)
		data = json.loads(output)

		assert "exception" in data
		assert "RuntimeError" in data["exception"]
		assert "json error test" in data["exception"]

	def test_format_includes_thread_id(self) -> None:
		record = self.logger.makeRecord(
			name="test.logger",
			level=logging.INFO,
			fn="test.py",
			lno=1,
			msg="thread test",
			args=(),
			exc_info=None,
		)
		output = self.formatter.format(record)
		data = json.loads(output)

		assert "thread" in data
		assert isinstance(data["thread"], int)

	def test_format_excludes_thread_when_none(self) -> None:
		record = self.logger.makeRecord(
			name="test.logger",
			level=logging.INFO,
			fn="test.py",
			lno=1,
			msg="no thread",
			args=(),
			exc_info=None,
		)
		# simulate thread being None/0
		record.thread = None
		output = self.formatter.format(record)
		data = json.loads(output)

		assert "thread" not in data

	def test_format_handles_non_serializable_extras(self) -> None:
		record = self.logger.makeRecord(
			name="test.logger",
			level=logging.INFO,
			fn="test.py",
			lno=1,
			msg="complex object",
			args=(),
			exc_info=None,
		)
		# add a non-json-serializable object
		record.complex_obj = object()
		output = self.formatter.format(record)

		# should not raise, uses default=str
		data = json.loads(output)
		assert "complex_obj" in data


class TestGetLogLevel:
	"""tests for log level detection."""

	def test_debug_mode_returns_debug(self) -> None:
		with patch("api.logging.boot_settings") as mock_settings:
			mock_settings.DEBUG = True
			mock_settings.ENV = "production"
			assert get_log_level() == logging.DEBUG

	def test_dev_env_returns_debug(self) -> None:
		with patch("api.logging.boot_settings") as mock_settings:
			mock_settings.DEBUG = False
			mock_settings.ENV = "dev"
			assert get_log_level() == logging.DEBUG

	def test_production_env_returns_info(self) -> None:
		with patch("api.logging.boot_settings") as mock_settings:
			mock_settings.DEBUG = False
			mock_settings.ENV = "production"
			assert get_log_level() == logging.INFO


class TestGetNoisyThirdPartyLogLevel:
	"""tests for noisy third-party logger level selection."""

	def test_debug_keeps_noisy_loggers_quiet(self) -> None:
		assert get_noisy_third_party_log_level(logging.DEBUG) == logging.WARNING

	def test_lower_than_debug_enables_noisy_loggers(self) -> None:
		assert get_noisy_third_party_log_level(logging.NOTSET) == logging.NOTSET


class TestConfigureLogging:
	"""tests for configure_logging function."""

	def teardown_method(self) -> None:
		# reset root logger after each test
		root = logging.getLogger()
		root.handlers = []
		root.setLevel(logging.WARNING)

	def test_configure_with_console_formatter(self) -> None:
		with patch("api.logging.boot_settings") as mock_settings:
			mock_settings.DEBUG = False
			mock_settings.ENV = "dev"
			configure_logging(json_logs=False)

		root = logging.getLogger()
		assert len(root.handlers) == 1
		assert isinstance(root.handlers[0].formatter, ConsoleFormatter)

	def test_configure_with_json_formatter(self) -> None:
		with patch("api.logging.boot_settings") as mock_settings:
			mock_settings.DEBUG = False
			mock_settings.ENV = "production"
			configure_logging(json_logs=True)

		root = logging.getLogger()
		assert len(root.handlers) == 1
		assert isinstance(root.handlers[0].formatter, JSONFormatter)

	def test_configure_with_custom_level(self) -> None:
		with patch("api.logging.boot_settings") as mock_settings:
			mock_settings.DEBUG = False
			mock_settings.ENV = "dev"
			configure_logging(level=logging.ERROR, json_logs=False)

		root = logging.getLogger()
		assert root.level == logging.ERROR

	def test_configure_clears_existing_handlers(self) -> None:
		"""Test that configure_logging replaces handlers with a single one."""
		root = logging.getLogger()
		# Add identifiable test handlers
		test_handler1 = logging.StreamHandler()
		test_handler1.name = "test_handler_1"
		test_handler2 = logging.StreamHandler()
		test_handler2.name = "test_handler_2"
		root.addHandler(test_handler1)
		root.addHandler(test_handler2)

		with patch("api.logging.boot_settings") as mock_settings:
			mock_settings.DEBUG = False
			mock_settings.ENV = "dev"
			configure_logging(json_logs=False)

		# After configure_logging, our test handlers should be gone
		handler_names = [h.name for h in root.handlers if h.name]
		assert "test_handler_1" not in handler_names
		assert "test_handler_2" not in handler_names
		# And there should be exactly one StreamHandler with our formatter
		our_handlers = [
			h
			for h in root.handlers
			if isinstance(h, logging.StreamHandler)
			and isinstance(h.formatter, ConsoleFormatter)
		]
		assert len(our_handlers) == 1

	def test_configure_suppresses_noisy_loggers(self) -> None:
		with patch("api.logging.boot_settings") as mock_settings:
			mock_settings.DEBUG = False
			mock_settings.ENV = "dev"
			configure_logging(json_logs=False)

		for name in NOISY_THIRD_PARTY_LOGGERS:
			logger = logging.getLogger(name)
			assert logger.level == logging.WARNING

	def test_configure_allows_noisy_loggers_for_absolute_lowest_level(self) -> None:
		with patch("api.logging.boot_settings") as mock_settings:
			mock_settings.DEBUG = False
			mock_settings.ENV = "dev"
			configure_logging(level=logging.NOTSET, json_logs=False)

		for name in NOISY_THIRD_PARTY_LOGGERS:
			logger = logging.getLogger(name)
			assert logger.level == logging.NOTSET

	def test_configure_uvicorn_propagates(self) -> None:
		with patch("api.logging.boot_settings") as mock_settings:
			mock_settings.DEBUG = False
			mock_settings.ENV = "dev"
			configure_logging(json_logs=False)

		for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
			logger = logging.getLogger(name)
			assert logger.propagate is True
			assert len(logger.handlers) == 0

	def test_auto_json_in_production(self) -> None:
		with patch("api.logging.boot_settings") as mock_settings:
			mock_settings.DEBUG = False
			mock_settings.ENV = "production"
			mock_settings.JSON_LOGS = True
			configure_logging()

		root = logging.getLogger()
		assert isinstance(root.handlers[0].formatter, JSONFormatter)

	def test_auto_console_in_dev(self) -> None:
		with patch("api.logging.boot_settings") as mock_settings:
			mock_settings.DEBUG = False
			mock_settings.ENV = "dev"
			mock_settings.JSON_LOGS = False
			configure_logging()

		root = logging.getLogger()
		assert isinstance(root.handlers[0].formatter, ConsoleFormatter)


class TestGetLogger:
	"""tests for get_logger function."""

	def test_returns_logger_instance(self) -> None:
		logger = get_logger("test.module")
		assert isinstance(logger, logging.Logger)
		assert logger.name == "test.module"

	def test_same_name_returns_same_logger(self) -> None:
		logger1 = get_logger("test.same")
		logger2 = get_logger("test.same")
		assert logger1 is logger2


class TestRequestIdContext:
	"""tests for request_id context variable."""

	def test_default_is_none(self) -> None:
		# ensure clean state
		assert request_id_ctx.get() is None

	def test_set_and_get(self) -> None:
		token = request_id_ctx.set("test-request-id")
		try:
			assert request_id_ctx.get() == "test-request-id"
		finally:
			request_id_ctx.reset(token)

	def test_reset_restores_previous(self) -> None:
		token1 = request_id_ctx.set("outer")
		token2 = request_id_ctx.set("inner")

		assert request_id_ctx.get() == "inner"
		request_id_ctx.reset(token2)
		assert request_id_ctx.get() == "outer"
		request_id_ctx.reset(token1)
		assert request_id_ctx.get() is None
