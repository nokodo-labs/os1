"""file text content sub-resource: extraction, storage, and vectors.

a file's body text is a sub-resource produced by deferred processing:
extraction (bytes -> text + chunks), store (the persisted text artifact), and
vectors (content vectors + single-file search).
"""

from api.v1.service.files.text_contents.extraction import (
	FileContentChunk,
	FileContentChunkBatch,
	chunk_loaded_text,
	is_direct_model_text_candidate,
	load_file_content_chunks,
	load_sdk_file_text,
	resolve_content_loader_chat_model,
	should_try_model_text,
)
from api.v1.service.files.text_contents.store import (
	FileContentLines,
	delete_extracted_text,
	has_extracted_text_child,
	read_extracted_text,
	read_file_content_lines,
	store_extracted_text,
)
from api.v1.service.files.text_contents.vectors import (
	CONTENT_VECTOR_COLLECTION_KEY,
	CONTENT_VECTOR_CONFIG_KEY,
	CONTENT_VECTOR_FINGERPRINT_KEY,
	CONTENT_VECTOR_PIPELINE_KEY,
	FileContentChunkHit,
	file_content_config_fp,
	file_content_fingerprint,
	file_content_stale_predicate,
	filter_unvectorized_files,
	load_file_content_chunks_reusing_stored_text,
	query_file_content,
	vectorize_file_content,
)


__all__ = [
	"CONTENT_VECTOR_COLLECTION_KEY",
	"CONTENT_VECTOR_CONFIG_KEY",
	"CONTENT_VECTOR_FINGERPRINT_KEY",
	"CONTENT_VECTOR_PIPELINE_KEY",
	"FileContentChunk",
	"FileContentChunkBatch",
	"FileContentChunkHit",
	"FileContentLines",
	"chunk_loaded_text",
	"delete_extracted_text",
	"file_content_config_fp",
	"file_content_fingerprint",
	"file_content_stale_predicate",
	"filter_unvectorized_files",
	"has_extracted_text_child",
	"is_direct_model_text_candidate",
	"load_file_content_chunks",
	"load_file_content_chunks_reusing_stored_text",
	"load_sdk_file_text",
	"query_file_content",
	"read_extracted_text",
	"read_file_content_lines",
	"resolve_content_loader_chat_model",
	"should_try_model_text",
	"store_extracted_text",
	"vectorize_file_content",
]
