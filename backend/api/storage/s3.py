"""S3-compatible storage backend (AWS S3, MinIO, R2, B2, etc.)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, TypedDict

import aiobotocore.session
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from api.storage.base import FileInfo, MimeType, StorageBackend


if TYPE_CHECKING:
	from types_aiobotocore_s3 import S3Client
	from types_aiobotocore_s3.type_defs import CompletedPartTypeDef


class _RetryConfig(TypedDict, total=False):
	total_max_attempts: int
	max_attempts: int
	mode: Literal["legacy", "standard", "adaptive"]


log = logging.getLogger(__name__)

# S3 HEAD returns "404" as a string code, not an int
_NOT_FOUND_CODES = {"404", "NoSuchKey"}


class S3StorageBackend(StorageBackend):
	"""async S3-compatible storage via aiobotocore.

	supports AWS S3, MinIO, Cloudflare R2, Backblaze B2, and any
	S3-compatible endpoint. multipart uploads are used for large files
	or stream inputs of unknown size.
	"""

	def __init__(
		self,
		*,
		bucket: str,
		region: str = "us-east-1",
		endpoint_url: str | None = None,
		access_key_id: str | None = None,
		secret_access_key: str | None = None,
		prefix: str = "",
		presigned_url_ttl: int = 3600,
		multipart_threshold: int = 100 * 1024 * 1024,
		multipart_chunk_size: int = 10 * 1024 * 1024,
		max_retries: int = 3,
		retry_mode: Literal["legacy", "standard", "adaptive"] = "adaptive",
	) -> None:
		super().__init__(name="s3")
		self._bucket = bucket
		self._prefix = prefix.rstrip("/") + "/" if prefix else ""
		self._presigned_url_ttl = presigned_url_ttl
		self._multipart_threshold = multipart_threshold
		self._multipart_chunk_size = multipart_chunk_size

		self._session = aiobotocore.session.AioSession()
		retry_cfg: _RetryConfig = {"max_attempts": max_retries, "mode": retry_mode}
		self._client_kwargs: dict[str, Any] = {
			"service_name": "s3",
			"region_name": region,
			"config": BotoConfig(
				retries=retry_cfg,
			),
		}
		if endpoint_url:
			self._client_kwargs["endpoint_url"] = endpoint_url
		if access_key_id:
			self._client_kwargs["aws_access_key_id"] = access_key_id
		if secret_access_key:
			self._client_kwargs["aws_secret_access_key"] = secret_access_key

		self._client_ctx: AbstractAsyncContextManager[S3Client] | None = None
		self._client: S3Client | None = None

	def _full_key(self, key: str) -> str:
		return f"{self._prefix}{key}" if self._prefix else key

	async def _get_client(self) -> S3Client:
		"""lazily create and cache the S3 client."""
		if self._client is None:
			ctx = self._session.create_client(**self._client_kwargs)
			self._client_ctx = ctx
			self._client = await ctx.__aenter__()
		client = self._client
		if client is None:
			msg = "S3 client not initialized"
			raise RuntimeError(msg)
		return client

	# -- interface --

	async def put(
		self,
		key: str,
		data: bytes | AsyncIterator[bytes],
		content_type: MimeType,
	) -> None:
		client = await self._get_client()
		full_key = self._full_key(key)

		if isinstance(data, (bytes, bytearray, memoryview)):
			raw = bytes(data)
			if len(raw) > self._multipart_threshold:
				await self._multipart_upload_bytes(client, full_key, raw, content_type)
			else:
				await client.put_object(
					Bucket=self._bucket,
					Key=full_key,
					Body=raw,
					ContentType=content_type,
				)
		else:
			await self._multipart_upload_stream(client, full_key, data, content_type)

	async def get(self, key: str) -> AsyncIterator[bytes]:
		client = await self._get_client()
		resp = await client.get_object(Bucket=self._bucket, Key=self._full_key(key))
		return _stream_s3_body(resp["Body"])

	async def delete(self, key: str) -> None:
		client = await self._get_client()
		await client.delete_object(Bucket=self._bucket, Key=self._full_key(key))

	async def exists(self, key: str) -> bool:
		return await self.stat(key) is not None

	async def stat(self, key: str) -> FileInfo | None:
		client = await self._get_client()
		try:
			resp = await client.head_object(
				Bucket=self._bucket, Key=self._full_key(key)
			)
		except ClientError as exc:
			error_code = exc.response.get("Error", {}).get("Code", "")
			if error_code in _NOT_FOUND_CODES:
				return None
			raise
		return FileInfo(
			size=resp["ContentLength"],
			content_type=resp.get("ContentType"),
			last_modified=resp.get("LastModified", datetime.now(UTC)),
			etag=resp.get("ETag"),
		)

	async def copy(self, src_key: str, dst_key: str) -> None:
		client = await self._get_client()
		await client.copy_object(
			Bucket=self._bucket,
			Key=self._full_key(dst_key),
			CopySource={
				"Bucket": self._bucket,
				"Key": self._full_key(src_key),
			},
		)

	async def get_url(self, key: str, expires_in: int | None = None) -> str | None:
		client = await self._get_client()
		ttl = expires_in if expires_in is not None else self._presigned_url_ttl
		url: str = await client.generate_presigned_url(
			"get_object",
			Params={"Bucket": self._bucket, "Key": self._full_key(key)},
			ExpiresIn=ttl,
		)
		return url

	async def close(self) -> None:
		if self._client_ctx is not None:
			await self._client_ctx.__aexit__(None, None, None)
			self._client_ctx = None
			self._client = None

	# -- multipart helpers --

	async def _multipart_upload_bytes(
		self,
		client: S3Client,
		key: str,
		data: bytes,
		content_type: str,
	) -> None:
		"""upload large bytes payload using multipart upload."""
		mpu = await client.create_multipart_upload(
			Bucket=self._bucket, Key=key, ContentType=content_type
		)
		upload_id = mpu["UploadId"]
		parts: list[CompletedPartTypeDef] = []
		try:
			offset = 0
			part_num = 1
			while offset < len(data):
				chunk = data[offset : offset + self._multipart_chunk_size]
				resp = await client.upload_part(
					Bucket=self._bucket,
					Key=key,
					PartNumber=part_num,
					UploadId=upload_id,
					Body=chunk,
				)
				parts.append({"ETag": resp["ETag"], "PartNumber": part_num})
				offset += self._multipart_chunk_size
				part_num += 1
			await client.complete_multipart_upload(
				Bucket=self._bucket,
				Key=key,
				UploadId=upload_id,
				MultipartUpload={"Parts": parts},
			)
		except BaseException:
			await client.abort_multipart_upload(
				Bucket=self._bucket, Key=key, UploadId=upload_id
			)
			raise

	async def _multipart_upload_stream(
		self,
		client: S3Client,
		key: str,
		data: AsyncIterator[bytes],
		content_type: str,
	) -> None:
		"""upload an async stream using multipart upload."""
		mpu = await client.create_multipart_upload(
			Bucket=self._bucket, Key=key, ContentType=content_type
		)
		upload_id = mpu["UploadId"]
		parts: list[CompletedPartTypeDef] = []
		try:
			buffer = bytearray()
			part_num = 1
			async for chunk in data:
				buffer.extend(chunk)
				while len(buffer) >= self._multipart_chunk_size:
					part_data = bytes(buffer[: self._multipart_chunk_size])
					del buffer[: self._multipart_chunk_size]
					resp = await client.upload_part(
						Bucket=self._bucket,
						Key=key,
						PartNumber=part_num,
						UploadId=upload_id,
						Body=part_data,
					)
					parts.append(
						{
							"ETag": resp["ETag"],
							"PartNumber": part_num,
						}
					)
					part_num += 1
			# flush remaining bytes
			if buffer or not parts:
				resp = await client.upload_part(
					Bucket=self._bucket,
					Key=key,
					PartNumber=part_num,
					UploadId=upload_id,
					Body=bytes(buffer),
				)
				parts.append(
					{
						"ETag": resp["ETag"],
						"PartNumber": part_num,
					}
				)
			await client.complete_multipart_upload(
				Bucket=self._bucket,
				Key=key,
				UploadId=upload_id,
				MultipartUpload={"Parts": parts},
			)
		except BaseException:
			await client.abort_multipart_upload(
				Bucket=self._bucket, Key=key, UploadId=upload_id
			)
			raise


# -- module-level helpers --


async def _stream_s3_body(body: Any) -> AsyncIterator[bytes]:
	"""yield chunks from an S3 streaming body."""
	async for chunk in body:
		yield chunk
