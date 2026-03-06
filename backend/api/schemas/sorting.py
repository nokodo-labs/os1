"""Shared sorting types.

These types are used by list endpoints across API versions.
"""

from __future__ import annotations

from typing import Literal


type SortDir = Literal["asc", "desc"]

type CommonSortBy = Literal[
	"created_at",
	"updated_at",
]


__all__ = [
	"CommonSortBy",
	"SortDir",
]
