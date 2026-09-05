"""single self-updating progress bar for test runs (replaces per-test spam).

active only on a TTY controller process; falls back to the default reporter
under -v, with --collect-only, in non-terminal output, and in xdist workers.
also replaces the warnings summary with one grouped by warning text (all modes).
"""

import re
import sys
from collections import Counter, deque
from collections.abc import Generator, Sized
from datetime import timedelta
from functools import partial
from math import exp
from pathlib import Path
from time import monotonic

import pytest
from _pytest.config import Config
from _pytest.main import Session
from _pytest.reports import BaseReport, TestReport
from _pytest.terminal import TerminalReporter, format_session_duration
from rich.console import Console, Group, RenderableType
from rich.constrain import Constrain
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
_ETA_RATE_TAU = 40.0
"""time constant, in seconds, of the exponentially weighted completion rate."""
_ETA_TRACK_TAU = 3.0
"""time constant, in seconds, the projected finish time is dragged toward a
new projection.

larger values steady the countdown but delay reacting to a real change of
pace, and past a few seconds that lag becomes outright inaccuracy: measured
over simulated runs, raising this to 15 pushed median error from 32% to 42%
while buying only 1pp fewer upward jumps.
"""
_ETA_MIN_COMPLETED = 12
"""completions required before an eta is shown instead of a placeholder."""
_ETA_WIDTH = 7
"""column width the eta readout is padded to, so the bar never resizes."""
_ETA_PLACEHOLDER = "--:--"
_ETA_CEILING = 35_999
"""largest eta rendered, in seconds; anything longer pins here.

the readout must never exceed ``_ETA_WIDTH`` or the bar resizes mid-run, and
``timedelta`` rolls over to an eight-character ``10:00:00`` past this point.
an estimate above ten hours only happens in a pathological stall, where the
exact figure carries no information anyway.
"""
_STARTUP_PHASES = (
	"spawning workers",
	"starting workers",
	"workers ready",
	"collecting tests",
)
"""xdist worker states, in the order each worker passes through them.

xdist tracks all four but only ever rewrites them onto a single throwaway
status line, so every phase before the last one scrolls past as plain text.
"""
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


def _eta_text(seconds: float | None, style: str) -> Text:
	if seconds is None:
		value = _ETA_PLACEHOLDER
	else:
		value = str(timedelta(seconds=min(int(seconds), _ETA_CEILING)))
	return Text(f"{value:>{_ETA_WIDTH}}", style=style)


class _ETAEstimator:
	"""projects when the run will finish, so the readout is a real countdown.

	estimating a *duration* means the number only moves when a test completes,
	which with many parallel workers arrives in bursts: the readout sits still
	and then jumps. so this tracks the projected finish *instant* instead, and
	the column renders ``finish - now``. between projections that ticks down a
	second per second on its own, and a finish instant is stationary (it is a
	fixed point in time, not a shrinking quantity), so smoothing it hard costs
	no accuracy and introduces none of the lag bias that smoothing a duration
	would.

	the underlying pace comes from an exponentially weighted completion rate;
	a hard sliding window makes the pace jump whenever a burst of completions
	falls off its far edge, whereas decaying both the completion count and the
	time they span leaves every sample contributing forever at a shrinking
	weight.
	"""

	def __init__(self, now: float, completed: float) -> None:
		self._updated = now
		self._completed = completed
		self._events = 0.0
		self._window = 0.0
		self._finish: float | None = None

	def update(self, now: float, completed: float, remaining: float) -> None:
		"""fold in the latest counts and re-aim the projected finish instant."""
		elapsed = now - self._updated
		if elapsed <= 0:
			return
		decay = exp(-elapsed / _ETA_RATE_TAU)
		self._events = self._events * decay + max(completed - self._completed, 0.0)
		self._window = self._window * decay + elapsed
		self._updated = now
		self._completed = completed
		if self._events <= 0 or self._window <= 0:
			return
		target = now + remaining * self._window / self._events
		if self._finish is None:
			self._finish = target
			return
		# drag the projection toward the new target at a rate set by wall time,
		# not by how often this happens to be called, so the render cadence
		# cannot change how quickly the countdown adapts.
		self._finish += (target - self._finish) * (1 - exp(-elapsed / _ETA_TRACK_TAU))

	def remaining_seconds(self, now: float) -> float | None:
		if self._finish is None:
			return None
		return max(self._finish - now, 0.0)


class _SmoothedETAColumn(ProgressColumn):
	"""counts down toward a smoothed projection of when the run will finish."""

	def __init__(self) -> None:
		super().__init__()
		self._estimators: dict[TaskID, _ETAEstimator] = {}

	def render(self, task: Task) -> Text:
		style = "progress.remaining"
		if task.total is None:
			return _eta_text(None, style)
		remaining = max(task.total - task.completed, 0.0)
		if remaining <= 0:
			return _eta_text(0.0, style)
		now = monotonic()
		estimator = self._estimators.get(task.id)
		if estimator is None:
			estimator = _ETAEstimator(now, task.completed)
			self._estimators[task.id] = estimator
		estimator.update(now, task.completed, remaining)
		if task.completed < _ETA_MIN_COMPLETED:
			return _eta_text(None, style)
		return _eta_text(estimator.remaining_seconds(now), style)


_WARNING_LINE = re.compile(r"(?P<path>.+?):(?P<lineno>\d+): (?P<text>.+)")


def _grouped_summary_warnings(reporter: TerminalReporter) -> None:
	"""warnings summary grouped by warning text: each unique warning prints
	once, above the source locations that emitted it.

	replaces ``TerminalReporter.summary_warnings``, which keys on the fully
	formatted message - the same warning from N source lines prints N times.
	"""
	if not reporter.hasopt("w"):
		return
	all_warnings = reporter.stats.get("warnings")
	if not all_warnings:
		return
	final = reporter._already_displayed_warnings is not None
	if final:
		reports = all_warnings[reporter._already_displayed_warnings :]
	else:
		reports = all_warnings
	reporter._already_displayed_warnings = len(reports)
	if not reports:
		return

	grouped: dict[str, Counter[str]] = {}
	for report in reports:
		first_line, _, _ = report.message.partition("\n")
		match = _WARNING_LINE.fullmatch(first_line)
		if match:
			text = match.group("text")
			location = f"{_relative(match.group('path'))}:{match.group('lineno')}"
		else:
			text = first_line or report.message
			location = report.nodeid or "<unknown location>"
		grouped.setdefault(text, Counter())[location] += 1

	title = "WARNINGS (final)" if final else "WARNINGS"
	total = sum(sum(c.values()) for c in grouped.values())
	_section(reporter, "warn", title, total, yellow=True)
	for text, locations in sorted(
		grouped.items(), key=lambda item: -sum(item[1].values())
	):
		reporter._tw.line(text, yellow=True)
		for location, count in locations.most_common():
			suffix = f" ({count}x)" if count > 1 else ""
			reporter._tw.line(f"  {location}{suffix}")


def _glyph(reporter: TerminalReporter, kind: str) -> str:
	"""marker for a section header, degrading to ascii where it cannot encode.

	on windows a console attached directly reports utf-8, but redirecting the
	same command to a file or pipe hands back a cp1252 stream that *raises*
	on these characters rather than substituting them - which would take the
	whole summary down exactly when the output is being captured. the real
	destination is consulted, not the reporter's writer, because rich may sit
	in between with an encoding of its own.
	"""
	preferred, fallback = _GLYPHS[kind]
	stream = getattr(reporter._tw, "_file", None)
	encoding = getattr(stream, "encoding", None) or getattr(
		sys.stdout, "encoding", None
	)
	if not encoding:
		return fallback
	try:
		preferred.encode(encoding)
	except UnicodeEncodeError, LookupError:
		return fallback
	return preferred


def _section(
	reporter: TerminalReporter, kind: str, label: str, count: int, **markup: bool
) -> None:
	"""blank line, then ``<glyph> LABEL <count>`` - the only anchor per block."""
	reporter._tw.line("")
	reporter._tw.line(f"{_glyph(reporter, kind)} {label} {count}", **markup)


def _nodeid_file(nodeid: str) -> str:
	return nodeid.split("::", 1)[0].replace("\\", "/")


def _relative(path: str) -> str:
	"""shorten a path to be relative to the rootdir where possible."""
	text = path.strip().replace("\\", "/")
	try:
		return Path(text).resolve().relative_to(Path.cwd()).as_posix()
	except ValueError, OSError:
		return text


_TB_LOCATION = re.compile(r"^(?P<path>.+?):(?P<lineno>\d+):(?P<rest>.*)$")
_WORKER_INFO = re.compile(r"^\[gw\d+\]\s+\S+\s+--\s+Python\s+\S+")
"""xdist's per-report ``[gw3] win32 -- Python 3.14.5 C:\\...\\python.exe`` line."""
_SOURCE_GUTTER = 4
"""columns pytest indents traceback source rows by, before their own indent."""
_GLYPHS = {
	"bad": ("\u2717", "x"),
	"good": ("\u2713", "+"),
	"warn": ("\u26a0", "!"),
	"skip": ("\u25cb", "-"),
}
"""section markers as ``(preferred, ascii fallback)``.

one marker per section header, never per row: a glyph costs a token or two
every time it appears, so putting one on each of a thousand failures would
undo the compaction it is decorating.
"""
_STYLES = {
	"bad": {"red": True, "bold": True},
	"good": {"green": True, "bold": True},
	"warn": {"yellow": True, "bold": True},
	"skip": {"yellow": True},
}
_KINDS = {
	"skipped": "skip",
	"xfailed": "skip",
	"xpassed": "warn",
	"passed": "good",
	"failed": "bad",
	"error": "bad",
}

_TAIL_FOOTER = re.compile(r"^ {2}\S*:\d+ [A-Z]\w*(?:Error|Exception|Exit|Warning)?$")
"""``--tb=long``'s closing ``path:line ExceptionType`` line for an entry."""


def _compact_body(rep: BaseReport) -> tuple[str, ...]:
	"""rewrite a traceback into the same information, minus the padding.

	drops blank filler rows, trims pytest's four-space ``E   `` gutter to two,
	and elides anything the nodeid printed directly above already states: the
	file path on frames inside the failing test's own file, and the name of
	the test function itself.
	"""
	own = _nodeid_file(rep.nodeid)
	own_func = rep.nodeid.rpartition("::")[2].partition("[")[0]
	lines: list[str] = []
	text = rep.longreprtext
	for raw in text.splitlines():
		line = raw.rstrip()
		stripped = line.strip()
		if not stripped or stripped == "E":
			continue
		if _WORKER_INFO.match(stripped):
			# under xdist every report is prefixed with the worker's platform,
			# python version and interpreter path; identical on every failure.
			continue
		if line.startswith("E "):
			lines.append(f"E {line[1:].lstrip()}")
			continue
		if lines and lines[-1].startswith("E ") and not raw[:1].strip():
			# continuation of the exception block above (assertion diffs and
			# the like); keep it in the same gutter so it reads as one unit.
			lines.append(f"E {stripped}")
			continue
		match = _TB_LOCATION.match(line)
		if match:
			path = _relative(match.group("path"))
			rest = match.group("rest").strip()
			if rest == f"in {own_func}":
				rest = ""
			where = "" if path == own else path
			lines.append(f"  {where}:{match.group('lineno')} {rest}".rstrip())
			continue
		# source rows keep their own indentation - in python it is syntax -
		# but pytest's leading gutter is re-based to two columns.
		body = line[_SOURCE_GUTTER:] if line[:_SOURCE_GUTTER].isspace() else stripped
		lines.append(f"    {body}".rstrip())
	if len(lines) > 1 and _TAIL_FOOTER.match(lines[-1]):
		# --tb=long closes each entry with a "location ExceptionType" footer.
		# the type already appears on the E line, but the location may be the
		# only one in the entry, so it is hoisted to the front rather than
		# dropped - failures read location-first everywhere else.
		lines.insert(0, lines.pop().rsplit(" ", 1)[0])
	if not any(line.startswith("  ") for line in lines):
		# --tb=line prints the exception alone; its location lives only on the
		# report, and without it nothing says where the failure happened.
		crash = getattr(getattr(rep, "longrepr", None), "reprcrash", None)
		if crash is not None:
			path = _relative(str(crash.path))
			where = "" if path == own else path
			lines.insert(0, f"  {where}:{crash.lineno}")
	return tuple(lines)


def _compact_sections(reporter: TerminalReporter, rep: BaseReport) -> list[str]:
	showcapture = reporter.config.option.showcapture
	if showcapture == "no":
		return []
	out: list[str] = []
	for secname, content in rep.sections:
		if showcapture != "all" and showcapture not in secname:
			continue
		body = content.rstrip()
		if not body:
			continue
		label = secname.replace("Captured ", "").replace(" call", "")
		out.append(f"  [{label}]")
		out.extend(f"    {line}" for line in body.splitlines())
	return out


def _compact_detail_summary(
	reporter: TerminalReporter, which: str, title: str, color: str
) -> None:
	"""print each distinct failure once, listing every test that produced it.

	pytest prints a full traceback per test, so a parametrized case that fails
	the same way in thirty variants is printed thirty times. reports whose
	rendered body is byte-identical share one copy, with every affected nodeid
	stacked above it.

	only exact duplicates are folded. grouping merely similar tracebacks -
	same exception from different call sites - was tried and rejected: it
	strands each test's own frames away from the error explaining them.
	"""
	if reporter.config.option.tbstyle == "no":
		return
	reports: list[BaseReport] = reporter.getreports(which)
	if not reports:
		return
	groups: dict[tuple[str, ...], list[BaseReport]] = {}
	for rep in reports:
		body = _compact_body(rep) + tuple(_compact_sections(reporter, rep))
		groups.setdefault(body, []).append(rep)
	_section(reporter, "bad", title, len(reports), **{color: True, "bold": True})
	for body, reps in groups.items():
		for rep in reps:
			nodeid = rep.nodeid.replace("\\", "/")
			when = getattr(rep, "when", None)
			suffix = f" ({when})" if which == "error" and when != "call" else ""
			# nodeids sit flush left and their detail is indented, so no row
			# marker is needed to tell them apart. one would cost a token on
			# every line - a thousand failures, a thousand tokens.
			reporter._tw.line(f"{nodeid}{suffix}", **{color: True})
		for line in body:
			reporter._tw.line(line)


def _compact_summary_errors(reporter: TerminalReporter) -> None:
	_compact_detail_summary(reporter, "error", "ERRORS", "red")


def _compact_summary_failures(reporter: TerminalReporter) -> None:
	_compact_detail_summary(reporter, "failed", "FAILURES", "red")


def _compact_summary_passes(
	reporter: TerminalReporter, which: str, title: str, opt: str
) -> None:
	"""show captured output from passing tests, and nothing when there is none.

	the stock version writes its banner before checking whether any report
	actually carries output, so ``-rA`` always emits an empty ``PASSES`` block.
	"""
	if reporter.config.option.tbstyle == "no" or not reporter.hasopt(opt):
		return
	reports: list[BaseReport] = [
		rep for rep in reporter.getreports(which) if rep.sections
	]
	if not reports:
		return
	_section(reporter, "good", title, len(reports), green=True, bold=True)
	for rep in reports:
		reporter._tw.line(rep.nodeid.replace("\\", "/"), green=True)
		for line in _compact_sections(reporter, rep):
			reporter._tw.line(line)


def _reason_of(rep: BaseReport) -> str:
	reason = str(getattr(rep, "wasxfail", "") or "")
	longrepr = rep.longrepr
	if not reason and isinstance(longrepr, tuple) and len(longrepr) == 3:
		reason = str(longrepr[2])
	if not reason:
		# with --tb=no nothing else reports why a test failed, so the crash
		# message is the only record. only its first line is kept: the rest
		# is the assertion diff, which is what --tb=no asked not to see.
		crash = getattr(longrepr, "reprcrash", None)
		if crash is not None:
			reason = str(crash.message).splitlines()[0]
	return reason.removeprefix("Skipped: ").strip()


def _location_of(rep: BaseReport) -> str:
	longrepr = rep.longrepr
	if isinstance(longrepr, tuple) and len(longrepr) == 3:
		# skips carry no nodeid worth printing - the file and line is what
		# identifies them - but everything else is addressable by nodeid.
		return f"{_relative(str(longrepr[0]))}:{longrepr[1]}"
	nodeid = rep.nodeid.replace("\\", "/")
	crash = getattr(longrepr, "reprcrash", None)
	if crash is not None and _nodeid_file(nodeid):
		return f"{nodeid}:{crash.lineno}"
	return nodeid


def _compact_short_test_summary(reporter: TerminalReporter) -> None:
	"""list only outcomes that have no detail section of their own.

	pytest's short summary repeats every failure it just printed in full;
	skips and xfails are the only entries that add anything, so only those
	are kept, folded by reason the same way warnings are.
	"""
	if not reporter.reportchars:
		return
	wanted = {"s": "skipped", "x": "xfailed", "X": "xpassed", "p": "passed"}
	labels = {
		"skipped": "SKIP",
		"xfailed": "XFAIL",
		"xpassed": "XPASS",
		"passed": "PASS",
	}
	if reporter.config.option.tbstyle == "no":
		# nothing printed a traceback, so the one-liners are the only record.
		wanted |= {"f": "failed", "E": "error"}
		labels |= {"failed": "FAIL", "error": "ERROR"}
	for char in reporter.reportchars:
		stat = wanted.get(char)
		if stat is None:
			continue
		reports: list[BaseReport] = reporter.stats.get(stat, [])
		if not reports:
			continue
		grouped: dict[str, list[str]] = {}
		for rep in reports:
			grouped.setdefault(_reason_of(rep), []).append(_location_of(rep))
		kind = "bad" if stat in ("failed", "error") else _KINDS[stat]
		_section(reporter, kind, labels[stat], len(reports), **_STYLES[kind])
		for reason, locations in sorted(grouped.items(), key=lambda i: -len(i[1])):
			# with no reason to head the block there is nothing to indent
			# under, so the entries stand on their own.
			indent = "  " if reason else ""
			if reason:
				reporter._tw.line(reason, **_STYLES[kind])
			for location in locations:
				reporter._tw.line(f"{indent}{location}")


_SEP_EXC_PREFIX = re.compile(r"^[\w.]+(?:Error|Exception|Interrupted|Exit):\s+")
_SEP_DIGITS = re.compile(r"\d+")


def _compact_write_sep(
	reporter: TerminalReporter,
	seen: set[str],
	sep: str,
	title: str | None = None,
	fullwidth: int | None = None,
	**markup: bool,
) -> None:
	"""write a banner's title as a plain line, once.

	stock banners pad their title to the full terminal width with ``=`` or
	``!``; the padding carries nothing. an interrupted run is also announced
	twice, by the session and again by xdist wrapping it in an exception
	("stopping after 10 failures" then "Interrupted: stopping after 1
	failures"), so titles that differ only in their exception prefix or in
	their numbers are treated as the same announcement.
	"""
	_ = sep, fullwidth
	if not title:
		# a rule with no title is pure decoration.
		return
	key = _SEP_DIGITS.sub("#", _SEP_EXC_PREFIX.sub("", title).strip().lower())
	if key in seen:
		return
	seen.add(key)
	reporter.ensure_newline()
	reporter._tw.line(title, **markup)


def _compact_summary_stats(reporter: TerminalReporter) -> None:
	if reporter.verbosity < -1:
		return
	parts, main_color = reporter.build_summary_stats_line()
	duration = format_session_duration(reporter._session_start.elapsed().seconds)
	line = ", ".join(text for text, _ in parts)
	# the verdict is what gets read first, so it carries the run's outcome as
	# a marker: green only when nothing failed, errored or went unexpectedly.
	kind = {"green": "good", "yellow": "warn"}.get(main_color, "bad")
	reporter._tw.line("")
	reporter._tw.line(
		f"{_glyph(reporter, kind)} {line} in {duration}",
		**{main_color: True, "bold": True},
	)


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
	reporter = config.pluginmanager.getplugin("terminalreporter")
	if not isinstance(reporter, TerminalReporter):
		return
	# the stock summaries are written for humans skimming a scrollback: banner
	# separators padded to the terminal width, a full traceback per failing
	# test even when fifty of them share one, then a short summary repeating
	# every failure a third time. these keep the same information and drop the
	# repetition.
	reporter.summary_warnings = partial(_grouped_summary_warnings, reporter)
	reporter.summary_errors = partial(_compact_summary_errors, reporter)
	reporter.summary_failures = partial(_compact_summary_failures, reporter)
	reporter.summary_passes = partial(
		_compact_summary_passes, reporter, "passed", "PASSES", "P"
	)
	reporter.summary_xpasses = partial(
		_compact_summary_passes, reporter, "xpassed", "XPASSES", "X"
	)
	reporter.short_test_summary = partial(_compact_short_test_summary, reporter)
	reporter.summary_stats = partial(_compact_summary_stats, reporter)
	reporter.write_sep = partial(_compact_write_sep, reporter, set())
	if not _should_activate(config):
		return
	plugin = LiveProgressPlugin(reporter)
	config.pluginmanager.register(plugin, "live_progress")
	if config.pluginmanager.hasplugin("xdist"):
		config.pluginmanager.register(_XdistPhasePlugin(plugin), "live_progress_xdist")


class _XdistPhasePlugin:
	"""mirrors xdist's worker bring-up into the startup bars.

	xdist advances every worker through spawn -> start -> ready -> collect,
	each via its own hook, but only ever rewrites them onto one throwaway
	status line. these hooks are kept out of the main plugin and registered
	only when xdist is loaded: pytest rejects a plugin declaring hooks whose
	specs no such plugin defines, so simply having them present would abort
	any run started with ``-p no:xdist``.
	"""

	def __init__(self, owner: LiveProgressPlugin) -> None:
		self._owner = owner

	def pytest_xdist_setupnodes(self, specs: Sized) -> None:
		self._owner.begin_startup(len(specs))

	def pytest_xdist_newgateway(self, gateway: object) -> None:
		_ = gateway
		self._owner.advance_phase("spawning workers")

	def pytest_testnodeready(self, node: object) -> None:
		_ = node
		self._owner.advance_phase("starting workers")

	def pytest_xdist_node_collection_finished(
		self, node: object, ids: list[str]
	) -> None:
		# each worker reports the full id list once collected, so its length
		# is the run total.
		_ = node
		self._owner.advance_phase("workers ready")
		self._owner.set_total(len(ids))


class _MutedFile:
	"""file stand-in that discards writes while the live display is active."""

	def write(self, _text: str) -> int:
		return 0

	def flush(self) -> None:
		return None


class LiveProgressPlugin:
	"""renders the live progress display and mutes the standard reporter."""

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
		self._startup = Progress(
			SpinnerColumn(),
			TextColumn("[progress.description]{task.description}"),
			BarColumn(bar_width=None),
			MofNCompleteColumn(),
			TextColumn("[dim]elapsed[/]"),
			TimeElapsedColumn(),
			console=self._console,
			auto_refresh=False,
		)
		self._task_id: TaskID | None = None
		self._recent: deque[tuple[str, str, str]] = deque(maxlen=_RECENT_WINDOW)
		self._seen: set[str] = set()
		self._live: Live | None = None
		self._total = 0
		self._phase_tasks: dict[str, TaskID] = {}
		self._phase_counts: dict[str, int] = dict.fromkeys(_STARTUP_PHASES, 0)
		self._workers = 0

	def pytest_collection_finish(self, session: Session) -> None:
		# non-xdist path: the controller itself knows the count here.
		if session.testscollected:
			self.set_total(session.testscollected)

	def begin_startup(self, workers: int) -> None:
		"""open a bar per bring-up phase, once the worker count is known."""
		self._workers = workers
		if self._phase_tasks or self._workers <= 0:
			return
		for phase in _STARTUP_PHASES:
			self._phase_tasks[phase] = self._startup.add_task(
				phase, total=self._workers, start=False
			)
		self._start()

	def advance_phase(self, phase: str) -> None:
		task_id = self._phase_tasks.get(phase)
		if task_id is None:
			return
		count = self._phase_counts[phase] + 1
		if count > self._workers:
			return
		self._phase_counts[phase] = count
		if count == 1:
			self._startup.start_task(task_id)
		self._startup.update(task_id, completed=count)
		self._refresh()

	@pytest.hookimpl(hookwrapper=True)
	def pytest_runtestloop(self, session: Session) -> Generator[None]:
		_ = session
		# xdist processes its collection events inside this loop, so the display
		# is usually already running by now; without xdist this is the start.
		self._start()
		try:
			yield
		finally:
			self._stop()

	def pytest_runtest_logreport(self, report: TestReport) -> None:
		if not self._is_test_done(report) or report.nodeid in self._seen:
			return
		self._finish_startup()
		self._seen.add(report.nodeid)
		outcome = self._outcome(report)
		if self._task_id is not None:
			self._progress.advance(self._task_id, 1)
		style = _OUTCOME_STYLES.get(outcome, "white")
		marker = _OUTCOME_MARKERS.get(outcome, outcome.upper())
		worker = self._worker_label(report)
		self._recent.append((style, worker, f"{marker:>5}  {report.nodeid}"))
		self._refresh()

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

	def set_total(self, total: int) -> None:
		if total <= self._total:
			return
		self._total = total
		if self._task_id is not None:
			self._progress.update(self._task_id, total=total)

	def _finish_startup(self) -> None:
		"""top the startup bars off once the first test result lands.

		the collection phase has no per-worker completion hook, so it is closed
		out here: by the time a test reports, every worker has finished
		collecting by definition.
		"""
		phase = "collecting tests"
		if self._phase_counts.get(phase) == self._workers:
			return
		for name, task_id in self._phase_tasks.items():
			self._phase_counts[name] = self._workers
			self._startup.start_task(task_id)
			self._startup.update(task_id, completed=self._workers)

	def _start(self) -> None:
		if self._live is not None:
			return
		total = self._total if self._total > 0 else None
		self._task_id = self._progress.add_task("running tests", total=total)
		self._reporter._tw._file = _MutedFile()
		# xdist's worker-status line is rewritten in place and left without a
		# trailing newline, so erase it before the live region claims the row.
		self._real_file.write("\r\x1b[2K")
		self._real_file.flush()
		self._live = Live(
			self._render(),
			console=self._console,
			refresh_per_second=12,
			transient=True,
		)
		self._live.start()

	def _refresh(self) -> None:
		if self._live is not None:
			self._live.update(self._render())

	def _stop(self) -> None:
		if self._live is not None:
			self._live.update(self._render())
			self._live.stop()
			self._live = None
		self._reporter._tw._file = self._real_file

	def _render(self) -> RenderableType:
		# every frame is the same height and no row reaches the final column:
		# a row that fills the terminal width makes it auto-wrap, and rich then
		# rewinds fewer lines than were actually drawn, stranding stale frames.
		rows: list[RenderableType] = []
		if self._phase_tasks:
			rows.append(self._startup)
		rows.append(self._progress)
		rows.extend(
			self._recent_row(style, worker, label)
			for style, worker, label in self._recent
		)
		rows.extend(Text("") for _ in range(_RECENT_WINDOW - len(self._recent)))
		return Constrain(Group(*rows), width=max(self._console.size.width - 1, 1))

	def _recent_row(self, style: str, worker: str, label: str) -> Text:
		row = Text(no_wrap=True, overflow="ellipsis")
		if worker:
			row.append(f"{'[' + worker + ']':<7}", style="dim")
		row.append(label, style=style)
		return row
