"""shared error response schemas.

these schemas follow RFC 9457 (problem details for HTTP APIs).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ValidationIssue(BaseModel):
	"""single validation issue from request parsing/validation."""

	model_config = ConfigDict(extra="ignore")

	type: str
	loc: list[str | int]
	message: str
	input: object | None = None
	context: dict[str, object] | None = None


class ProblemDetails(BaseModel):
	"""RFC 9457 problem details response."""

	model_config = ConfigDict(extra="allow")

	type: str = Field(
		"about:blank",
		min_length=1,
		description="URI reference that identifies the problem type.",
	)
	title: str = Field(..., min_length=1, description="short, human-readable summary")
	status: int = Field(..., ge=100, le=599, description="HTTP status code")
	detail: str | None = Field(
		default=None,
		description="human-readable explanation specific to this occurrence",
	)
	instance: str | None = Field(
		default=None,
		description="URI reference that identifies the specific occurrence",
	)

	# extensions (non-standard members) allowed by RFC 9457
	request_id: str | None = None
	data: object | None = None


class ValidationProblemDetails(ProblemDetails):
	"""RFC 9457 validation problem details.

	RFC 9457 does not standardize a validation error shape; we include
	`errors` as an extension.
	"""

	type: Literal["urn:nokodo:validation-error"] = "urn:nokodo:validation-error"
	title: Literal["validation error"] = "validation error"
	status: Literal[422] = 422
	errors: list[ValidationIssue]
