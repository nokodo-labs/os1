"""thumbnail derivatives for user files (stub).

a thumbnail is an internal derivative file (source=THUMBNAIL) generated from a
parent that has a visual rendering. only the capability gate and derived-file
plumbing exist here; pixel generation is not implemented yet, so this is not
wired into the processing pipeline or the maintenance sweep - doing so before a
generator exists would make thumbnailable files perpetually "due".
"""

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import File, FileSource
from api.models.model import InputModality
from api.v1.service.files.derived_files import (
	delete_derived_file,
	write_derived_file,
)
from api.v1.service.files.modalities import file_input_modality


THUMBNAIL_KEY_PREFIX = "thumbnail"
THUMBNAIL_MIME = "image/webp"

# modalities whose files have a visual rendering a thumbnail can be made from.
_THUMBNAILABLE_MODALITIES = frozenset(
	{InputModality.IMAGES, InputModality.VIDEO, InputModality.DOCUMENTS}
)


def can_generate_thumbnail(file: File) -> bool:
	"""return whether a file has a visual rendering to thumbnail."""
	modality = file_input_modality(file.filename, file.mime_type)
	return modality in _THUMBNAILABLE_MODALITIES


async def generate_thumbnail_bytes(file: File, session: AsyncSession) -> bytes:
	"""render a thumbnail image for a file. not implemented yet."""
	raise NotImplementedError("thumbnail generation is not implemented yet")


async def store_thumbnail(file: File, session: AsyncSession) -> File | None:
	"""generate and persist a file's thumbnail as a derived file.

	no-ops for files without a visual rendering. returns the derived file, or
	None when the file cannot be thumbnailed.
	"""
	if not can_generate_thumbnail(file):
		return None
	data = await generate_thumbnail_bytes(file, session)
	return await write_derived_file(
		file,
		FileSource.THUMBNAIL,
		data,
		THUMBNAIL_MIME,
		THUMBNAIL_KEY_PREFIX,
		session,
	)


async def delete_thumbnail(file: File, session: AsyncSession) -> None:
	"""delete a file's thumbnail derived file and its bytes, if any."""
	await delete_derived_file(file.id, FileSource.THUMBNAIL, session)
