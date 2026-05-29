"""prompt service package facade."""

from jinja2 import TemplateNotFound

from api.v1.service.prompts.cache import (
	get_cached_prompt_templates,
	invalidate_prompt_template_cache,
	list_prompt_templates,
	set_cached_prompt_templates,
)
from api.v1.service.prompts.external import (
	ExternalPromptSource,
	load_external_prompt_placeholders,
	register_external_prompt_source,
	render_external_prompt_content_map,
)
from api.v1.service.prompts.runtime import (
	SENTINEL_CHAT_CONTEXT,
	SENTINEL_CHAT_WINDOW_INFO,
	SENTINEL_CITATION_SOURCES,
	SENTINEL_REFERENCED_ATTACHMENTS,
	SENTINEL_USER_MEMORIES,
	PromptValidationError,
	build_prompt_variables,
	http_error_from_validation,
	normalize_command,
	render_agent_instructions,
	render_inline_with_prompts,
	render_prompt_from_db,
	render_prompt_from_map,
	validate_prompt_content,
)
from api.v1.service.prompts.service import (
	count_prompts,
	create_prompt,
	delete_prompt,
	get_prompt,
	list_prompts,
	update_prompt,
)


__all__ = [
	"SENTINEL_CHAT_CONTEXT",
	"SENTINEL_CHAT_WINDOW_INFO",
	"SENTINEL_CITATION_SOURCES",
	"SENTINEL_REFERENCED_ATTACHMENTS",
	"SENTINEL_USER_MEMORIES",
	"ExternalPromptSource",
	"PromptValidationError",
	"TemplateNotFound",
	"build_prompt_variables",
	"count_prompts",
	"create_prompt",
	"delete_prompt",
	"get_cached_prompt_templates",
	"get_prompt",
	"http_error_from_validation",
	"invalidate_prompt_template_cache",
	"list_prompt_templates",
	"list_prompts",
	"load_external_prompt_placeholders",
	"normalize_command",
	"register_external_prompt_source",
	"render_agent_instructions",
	"render_external_prompt_content_map",
	"render_inline_with_prompts",
	"render_prompt_from_db",
	"render_prompt_from_map",
	"set_cached_prompt_templates",
	"update_prompt",
	"validate_prompt_content",
]
