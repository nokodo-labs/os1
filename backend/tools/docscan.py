"""report declared symbols that carry no docstring.

every function, class, module-level variable, and class attribute we declare is
a symbol someone reads on hover from a call site - so each one states what it
IS, and none restates what the code already shows.

usage (from ``backend/``)::

	uv run python tools/docscan.py api/v1/service/runs
	uv run python tools/docscan.py --summary api nokodo_ai
	uv run python tools/docscan.py --exit-code api/models/message.py
"""

import argparse
import ast
from collections.abc import Iterator
from pathlib import Path


SKIP_NAMES = frozenset({"logger", "__all__"})
"""module-level names whose purpose is fixed by convention, not by us."""

SKIP_ATTRS = frozenset({"model_config"})
"""class attributes that configure a framework rather than declare data."""

SKIP_DIRS = frozenset(
	{
		"__pycache__",
		".venv",
		"migrations",
		"node_modules",
		"stubs",
	}
)
"""directories a sweep never reports on: generated, vendored, or not ours."""


def _has_attr_docstring(body: list[ast.stmt], index: int) -> bool:
	"""whether the statement at ``index`` is followed by its docstring.

	PEP 258 attribute docstrings are a bare string expression after the
	assignment; nothing binds them to it, so position is the whole contract.
	"""
	nxt = body[index + 1] if index + 1 < len(body) else None
	return (
		isinstance(nxt, ast.Expr)
		and isinstance(nxt.value, ast.Constant)
		and isinstance(nxt.value.value, str)
	)


def _targets(node: ast.stmt) -> list[str]:
	"""the names one assignment or type alias declares."""
	if isinstance(node, ast.AnnAssign):
		return [node.target.id] if isinstance(node.target, ast.Name) else []
	if isinstance(node, ast.Assign):
		return [t.id for t in node.targets if isinstance(t, ast.Name)]
	if isinstance(node, ast.TypeAlias):
		return [node.name.id]
	return []


def _is_overload(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
	"""whether a def is a typing overload, which documents its implementation."""
	for decorator in node.decorator_list:
		name = (
			decorator.attr
			if isinstance(decorator, ast.Attribute)
			else getattr(decorator, "id", None)
		)
		if name == "overload":
			return True
	return False


def _label(path: Path, root: Path) -> str:
	"""the shortest readable form of a path, however it was given to us."""
	try:
		return str(path.resolve().relative_to(root))
	except ValueError:
		return str(path)


def scan(path: Path, root: Path | None = None) -> list[str]:
	"""every undocumented symbol in one file, as printable lines."""
	label_path = _label(path, root) if root else str(path)
	tree = ast.parse(path.read_text(encoding="utf-8"))
	out: list[str] = []

	if not ast.get_docstring(tree):
		out.append(f"{label_path}:1 module {path.stem}")

	def walk(body: list[ast.stmt], scope: str, kind: str) -> None:
		"""report this scope's declarations, then recurse into them."""
		for i, node in enumerate(body):
			if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
				label = f"{scope}{node.name}()"
				if not ast.get_docstring(node) and not _is_overload(node):
					out.append(f"{label_path}:{node.lineno} func {label}")
				walk(node.body, f"{label}.", "func")
			elif isinstance(node, ast.ClassDef):
				label = f"{scope}{node.name}"
				if not ast.get_docstring(node):
					out.append(f"{label_path}:{node.lineno} class {label}")
				walk(node.body, f"{label}.", "class")
			elif kind != "func" and isinstance(
				node, (ast.Assign, ast.AnnAssign, ast.TypeAlias)
			):
				# locals are not declared symbols; module vars and class
				# attributes are.
				for name in _targets(node):
					if name.startswith("__"):
						continue
					if kind == "module" and name in SKIP_NAMES:
						continue
					if kind == "class" and name in SKIP_ATTRS:
						continue
					if not _has_attr_docstring(body, i):
						what = "module-var" if kind == "module" else "attr"
						out.append(f"{label_path}:{node.lineno} {what} {scope}{name}")

	walk(tree.body, "", "module")
	return out


def python_files(targets: list[str]) -> Iterator[Path]:
	"""expand paths into python files, skipping what a sweep should not read."""
	for target in targets:
		path = Path(target)
		if path.is_file():
			yield path
			continue
		for found in sorted(path.rglob("*.py")):
			if SKIP_DIRS.isdisjoint(found.parts):
				yield found


def main() -> int:
	"""print undocumented symbols, or a per-file count with ``--summary``."""
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("targets", nargs="+", help="files or directories to scan")
	parser.add_argument(
		"--summary",
		action="store_true",
		help="print one count per file instead of every symbol",
	)
	parser.add_argument(
		"--exit-code",
		action="store_true",
		help="exit non-zero when anything is undocumented, for CI",
	)
	args = parser.parse_args()

	root = Path.cwd()
	total = 0
	for path in python_files(args.targets):
		try:
			issues = scan(path, root)
		except SyntaxError as error:
			print(f"{path}: SKIPPED, does not parse ({error.msg})")
			continue
		total += len(issues)
		if not issues:
			continue
		if args.summary:
			print(f"{len(issues):5}  {_label(path, root)}")
		else:
			for line in issues:
				print(line)

	print(f"--- {total} undocumented")
	return 1 if args.exit_code and total else 0


if __name__ == "__main__":
	raise SystemExit(main())
