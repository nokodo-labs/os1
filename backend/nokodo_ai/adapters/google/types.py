"""centralized Google GenAI SDK types for nokodo_ai adapters.

the goal is to keep all google-genai SDK imports in one place so adapter modules
stay small and type check cleanly.
"""

from __future__ import annotations

from google.genai.types import (
	Blob as GoogleBlob,
)
from google.genai.types import (
	Content as GoogleContent,
)
from google.genai.types import (
	FunctionCall as GoogleFunctionCall,
)
from google.genai.types import (
	FunctionCallingConfig as GoogleFunctionCallingConfig,
)
from google.genai.types import (
	FunctionDeclaration as GoogleFunctionDeclaration,
)
from google.genai.types import (
	FunctionResponse as GoogleFunctionResponse,
)
from google.genai.types import (
	GenerateContentConfig as GoogleGenerateContentConfig,
)
from google.genai.types import (
	GenerateContentResponse as GoogleGenerateContentResponse,
)
from google.genai.types import (
	Part as GooglePart,
)
from google.genai.types import (
	ThinkingConfig as GoogleThinkingConfig,
)
from google.genai.types import (
	ThinkingLevel as GoogleThinkingLevel,
)
from google.genai.types import (
	Tool as GoogleTool,
)
from google.genai.types import (
	ToolConfig as GoogleToolConfig,
)
from google.genai.types import (
	ToolListUnion as GoogleToolListUnion,
)


__all__ = [
	"GoogleBlob",
	"GoogleContent",
	"GoogleFunctionCall",
	"GoogleFunctionCallingConfig",
	"GoogleFunctionDeclaration",
	"GoogleFunctionResponse",
	"GoogleGenerateContentConfig",
	"GoogleGenerateContentResponse",
	"GooglePart",
	"GoogleTool",
	"GoogleToolConfig",
	"GoogleToolListUnion",
	"GoogleThinkingConfig",
	"GoogleThinkingLevel",
]
