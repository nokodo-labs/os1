"""google provider adapters."""

from __future__ import annotations

from .base import BaseGoogleAdapter
from .generate_content import GoogleGenerateContentAdapter


__all__ = [
	"BaseGoogleAdapter",
	"GoogleGenerateContentAdapter",
]
