"""helpers for list endpoint filtering and sorting."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import asc, desc, literal
from sqlalchemy.orm import InstrumentedAttribute, Mapped
from sqlalchemy.sql import ColumnElement, Select

from api.schemas.sorting import SortDir
from nokodo_ai.utils.typeid import assert_typeid


SortColumn = ColumnElement[Any] | InstrumentedAttribute[Any] | Mapped[Any]


def exact_typeid_filter(
	column: InstrumentedAttribute,
	query: str,
	typeid_prefix: str | None = None,
) -> ColumnElement[bool]:
	"""match a TypeID column exactly when q is a valid TypeID."""
	trimmed = query.strip()
	try:
		typeid = assert_typeid(trimmed)
	except ValueError:
		return literal(False)
	if typeid_prefix is not None and not typeid.startswith(f"{typeid_prefix}_"):
		return literal(False)
	return column == typeid


def _order_expr(column: SortColumn, sort_dir: SortDir) -> ColumnElement[Any]:
	if sort_dir == "asc":
		return asc(column)
	return desc(column)


def apply_sort(
	stmt: Select,
	sort_by: str,
	sort_dir: SortDir,
	columns: Mapping[str, SortColumn],
	tie_breaker: SortColumn | None = None,
) -> Select:
	column = columns.get(sort_by)
	if column is None:
		return stmt

	orderings: list[ColumnElement[Any]] = [_order_expr(column, sort_dir)]
	if tie_breaker is not None:
		orderings.append(_order_expr(tie_breaker, sort_dir))
	return stmt.order_by(*orderings)
