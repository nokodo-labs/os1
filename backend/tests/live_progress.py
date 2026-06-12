"""Single self-updating progress bar for test runs (replaces per-test spam).

Active only on a TTY controller process; falls back to the default reporter
under -v, with --collect-only, in non-terminal output, and in xdist workers.
"""

from __future__ import annotations

import sys
from collections import deque
from collections.abc import Generator
from datetime import timedelta
from time import monotonic

import pytest
from _pytest.config import Config
from _pytest.main import Session
from _pytest.reports import TestReport
from _pytest.terminal import TerminalReporter
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.progress import (
	BarColumn,
	MofNCompleteColumn,
	Progress,
	ProgressColumn,
	SpinnerColumn,
	Task,
	TaskID,
	TaskProgressColumn,
	TextColumn,
	TimeElapsedColumn,
)
from rich.text import Text


_RECENT_WINDOW = 8
_ETA_WINDOW_SECONDS = 20.0
_OUTCOME_STYLES = {
	"passed": "green",
	"failed": "bold red",
	"error": "bold red",
	"skipped": "yellow",
	"xfailed": "yellow",
	"xpassed": "magenta",
}
_OUTCOME_MARKERS = {
	"passed": "PASS",
	"failed": "FAIL",
	"error": "ERR",
	"skipped": "SKIP",
	"xfailed": "XFAIL",
	"xpassed": "XPASS",
}


def _should_activate(config: Config) -> bool:
	if hasattr(config, "workerinput"):
		# xdist worker subprocess; only the controller renders.
		return False
	if config.option.verbose > 0:
		# user asked for detail; leave the classic reporter in place.
		return False
	if config.getoption("collectonly", default=False):
		return False
	return sys.stdout.isatty()


class _SmoothedETAColumn(ProgressColumn):
	"""ETA from a sliding window of recent throughput, not instantaneous rate."""

	def __init__(self, window_seconds: float = _ETA_WINDOW_SECONDS) -> None:
		super().__init__()
		self._window = window_seconds
		self._samples: dict[TaskID, deque[tuple[float, float]]] = {}

	def render(self, task: Task) -> Text:
		style = "progress.remaining"
		if task.total is None:
			return Text("--:--", style=style)
		remaining = task.total - task.completed
		if remaining <= 0:
			return Text("0:00:00", style=style)
		now = monotonic()
		samples = self._samples.setdefault(task.id, deque())
		samples.append((now, task.completed))
		while len(samples) > 1 and now - samples[0][0] > self._window:
			samples.popleft()
		if len(samples) < 2:
			return Text("--:--", style=style)
		elapsed = samples[-1][0] - samples[0][0]
		done = samples[-1][1] - samples[0][1]
		if elapsed <= 0 or done <= 0:
			return Text("--:--", style=style)
		eta = remaining * elapsed / done
		return Text(str(timedelta(seconds=int(eta))), style=style)


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
	if not _should_activate(config):
		return
	reporter = config.pluginmanager.getplugin("terminalreporter")
	if not isinstance(reporter, TerminalReporter):
		return
	config.pluginmanager.register(LiveProgressPlugin(reporter), "live_progress")


class _MutedFile:
	"""File stand-in that discards writes while the live display is active."""

	def write(self, _text: str) -> int:
		return 0

	def flush(self) -> None:
		return None


class LiveProgressPlugin:
	"""Renders the live progress display and mutes the standard reporter."""

	def __init__(self, reporter: TerminalReporter) -> None:
		self._reporter = reporter
		self._real_file = reporter._tw._file
		self._console = Console(file=self._real_file, force_terminal=True)
		self._progress = Progress(
			SpinnerColumn(),
			TextColumn("[progress.description]{task.description}"),
			BarColumn(bar_width=None),
			TaskProgressColumn(),
			MofNCompleteColumn(),
			TextColumn("[dim]elapsed[/]"),
			TimeElapsedColumn(),
			TextColumn("[dim]eta[/]"),
			_SmoothedETAColumn(),
			console=self._console,
			auto_refresh=False,
		)
		self._task_id: TaskID | None = None
		self._recent: deque[tuple[str, str, str]] = deque(maxlen=_RECENT_WINDOW)
		self._seen: set[str] = set()
		self._live: Live | None = None
		self._total = 0

	def pytest_collection_finish(self, session: Session) -> None:
		# non-xdist path: the controller itself knows the count here.
		if session.testscollected:
			self._set_total(session.testscollected)

	def pytest_xdist_node_collection_finished(
		self, node: object, ids: list[str]
	) -> None:
		# xdist path: each worker reports the full id list once it has
		# collected, so its length is the run total.
		_ = node
		self._set_total(len(ids))

	@pytest.hookimpl(hookwrapper=True)
	def pytest_runtestloop(self, session: Session) -> Generator[None]:
		_ = session
		self._start()
		try:
			yield
		finally:
			self._stop()

	def pytest_runtest_logreport(self, report: TestReport) -> None:
		if not self._is_test_done(report) or report.nodeid in self._seen:
			return
		self._seen.add(report.nodeid)
		outcome = self._outcome(report)
		if self._task_id is not None:
			self._progress.advance(self._task_id, 1)
		style = _OUTCOME_STYLES.get(outcome, "white")
		marker = _OUTCOME_MARKERS.get(outcome, outcome.upper())
		worker = self._worker_label(report)
		self._recent.append((style, worker, f"{marker:>5}  {report.nodeid}"))
		if self._live is not None:
			self._live.update(self._render())

	def _worker_label(self, report: TestReport) -> str:
		# xdist attaches the worker node to each report on the controller.
		try:
			return str(report.node.gateway.id)
		except AttributeError:
			return ""

	def _is_test_done(self, report: TestReport) -> bool:
		if report.when == "call":
			return True
		return report.when == "setup" and report.outcome != "passed"

	def _outcome(self, report: TestReport) -> str:
		if report.when == "setup" and report.outcome != "passed":
			return "error" if report.failed else report.outcome
		return report.outcome

	def _set_total(self, total: int) -> None:
		if total <= self._total:
			return
		self._total = total
		if self._task_id is not None:
			self._progress.update(self._task_id, total=total)

	def _start(self) -> None:
		total = self._total if self._total > 0 else None
		self._task_id = self._progress.add_task("running tests", total=total)
		self._reporter._tw._file = _MutedFile()
		# xdist leaves its worker-status line without a trailing newline, so
		# drop to a fresh line before the live region takes over the terminal.
		self._real_file.write("\n")
		self._real_file.flush()
		self._live = Live(
			self._render(),
			console=self._console,
			refresh_per_second=12,
			transient=True,
		)
		self._live.start()

	def _stop(self) -> None:
		if self._live is not None:
			self._live.update(self._render())
			self._live.stop()
			self._live = None
		self._reporter._tw._file = self._real_file

	def _render(self) -> RenderableType:
		lines = Text()
		for style, worker, label in self._recent:
			if worker:
				lines.append(f"{'[' + worker + ']':<7}", style="dim")
			lines.append(label + "\n", style=style)
		return Group(self._progress, lines)
