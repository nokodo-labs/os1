"""shared sentinels."""

from typing import TYPE_CHECKING

from pydantic.experimental.missing_sentinel import MISSING


if TYPE_CHECKING:
	from typing_extensions import Sentinel as MissingType
else:
	MissingType = MISSING


__all__ = ["MISSING", "MissingType"]
