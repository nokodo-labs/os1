"""file service package facade."""

from api.v1.service.files.content_vectorization import (
	FileContentChunk,
	FileContentChunkBatch,
	load_file_content_chunks,
	vectorize_file_content,
)
from api.v1.service.files.description import update_file_description
from api.v1.service.files.processing import (
	process_file,
	process_file_content_vectorization,
	process_file_description,
)
from api.v1.service.files.search import search_files
from api.v1.service.files.service import (
	count_files,
	delete_content,
	delete_file,
	get_file,
	get_file_content,
	get_file_payload,
	get_file_url,
	ingest_file,
	list_files,
	read_content,
	read_file_base64,
	register_stored_file,
	restore_file,
	store_file,
	update_file,
	upload_file,
)
from api.v1.service.files.vectorization import (
	FILE_SPEC,
	remove_file_vectors,
	replace_all_file_vectors,
	replace_file_description_vectors,
	vectorize_all_files,
)


__all__ = [
	"FILE_SPEC",
	"FileContentChunk",
	"FileContentChunkBatch",
	"count_files",
	"delete_content",
	"delete_file",
	"get_file",
	"get_file_content",
	"get_file_payload",
	"get_file_url",
	"ingest_file",
	"list_files",
	"load_file_content_chunks",
	"process_file",
	"process_file_content_vectorization",
	"process_file_description",
	"read_content",
	"read_file_base64",
	"register_stored_file",
	"remove_file_vectors",
	"replace_all_file_vectors",
	"replace_file_description_vectors",
	"restore_file",
	"search_files",
	"store_file",
	"update_file",
	"update_file_description",
	"upload_file",
	"vectorize_file_content",
	"vectorize_all_files",
]
