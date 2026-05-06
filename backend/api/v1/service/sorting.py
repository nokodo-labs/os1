"""Sorting helpers for list endpoints."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import asc, desc
from sqlalchemy.orm import InstrumentedAttribute, Mapped
from sqlalchemy.sql import ColumnElement, Select

from api.schemas.sorting import SortDir


SortColumn = ColumnElement[Any] | InstrumentedAttribute[Any] | Mapped[Any]


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
