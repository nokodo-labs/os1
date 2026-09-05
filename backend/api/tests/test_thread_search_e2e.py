"""end-to-end thread search tests against a real in-memory qdrant.

the shared conftest stubs vectorstore CRUD for unit tests; this module
restores the real functions (captured at import time, before fixtures run)
so reconcile -> upsert -> filtered search -> fold -> anchor runs the real
pipeline. embeddings are replaced with a deterministic character-trigram
featurizer: lexically similar texts get similar vectors, which is enough to
exercise dense retrieval end-to-end without a provider. sparse/BM25 needs
fastembed local inference (not installed in test envs), so e2e runs in
DENSE mode; the sparse arm is covered by unit tests with faked hits.
"""

from __future__ import annotations

import hashlib
import math
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import Message, MessageType
from api.models.thread import Thread
from api.models.user import User
from api.permissions import DefaultResourceAccess
from api.schemas.search import SearchMode, SearchParams
from api.schemas.thread import ThreadSearchFilters
from api.settings import settings
from api.tests.factories import reconcile_one_thread
from api.tests.mocks import patch_vectorstore_ops
from api.v1.service import vectorstores as vectorstores_service
from api.v1.service.authentication import Principal
from api.v1.service.search.primitives import SearchHit
from api.v1.service.threads.search import _hybrid_search_threads, search_threads
from nokodo_ai.adapters.qdrant.vectorstores import QdrantVectorstoreAdapter
from nokodo_ai.embeddings import EmbeddingModel
from nokodo_ai.utils.security import hash_password
from nokodo_ai.vectorstores import Vectorstore


# captured at import time, before the autouse stub fixture replaces them.
_REAL_UPSERT = vectorstores_service.upsert_chunks
_REAL_DELETE = vectorstores_service.delete
_REAL_SEARCH = vectorstores_service.search

_DENSE = SearchParams(mode=SearchMode.DENSE)
_DIMS = 64


def _featurize(text: str) -> list[float]:
	"""deterministic character-trigram hash embedding (lexical similarity)."""
	vec = [0.0] * _DIMS
	lowered = text.lower()
	for i in range(max(len(lowered) - 2, 0)):
		trigram = lowered[i : i + 3]
		bucket = int(hashlib.md5(trigram.encode("utf-8")).hexdigest()[:8], 16)
		vec[bucket % _DIMS] += 1.0
	norm = math.sqrt(sum(v * v for v in vec)) or 1.0
	return [v / norm for v in vec]


@pytest.fixture
def real_vectorstore(monkeypatch: pytest.MonkeyPatch) -> None:
	"""restore real vectorstore ops against a private in-memory qdrant.

	get_vectorstore() revalidates the adapter on every call, which re-runs
	_init_client and hands each call a brand-new empty :memory: database.
	pinning one adapter and one Vectorstore per collection keeps every
	service call on the same store, like a real server deployment.
	"""
	monkeypatch.setattr(settings.assets.vector_database.qdrant, "url", ":memory:")
	vectorstores_service._vectorstore_adapter.cache_clear()
	vectorstores_service._cached_collection_name = None

	adapter = QdrantVectorstoreAdapter(location=":memory:")
	stores: dict[str, Vectorstore] = {}

	def _pinned_store(*, collection: str) -> Vectorstore:
		if collection not in stores:
			stores[collection] = Vectorstore.model_construct(
				collection=collection, adapter=adapter
			)
		return stores[collection]

	patch_vectorstore_ops(monkeypatch, get_vectorstore=_pinned_store)

	async def _dense_upsert(
		chunks: list,
		session: object,
		collection: str | None = None,
		store: object | None = None,
	) -> None:
		# sparse indexing needs fastembed local inference (not installed in
		# test envs); everything else runs the real pipeline.
		if not chunks:
			return
		coll = collection or await vectorstores_service.get_collection(session)
		vs = _pinned_store(collection=coll)
		await vs.ensure_collection(vector_size=len(chunks[0].embedding))
		await vs.add(chunks, sparse=False)

	patch_vectorstore_ops(
		monkeypatch,
		upsert_chunks=_dense_upsert,
		delete=_REAL_DELETE,
		search=_REAL_SEARCH,
	)

	async def _fake_embed(
		self: EmbeddingModel, texts: list[str], input_type: str | None = None
	) -> list[list[float]]:
		_ = self, input_type
		return [_featurize(text) for text in texts]

	monkeypatch.setattr(EmbeddingModel, "embed", _fake_embed)


def _uid() -> str:
	return uuid4().hex[:8]


def _user(suffix: str) -> User:
	return User(
		email=f"{suffix}@e2e.test",
		username=f"e2e_{suffix}",
		hashed_password=hash_password("x"),
		is_active=True,
	)


def _principal(user: User) -> Principal:
	return Principal.for_user(
		user=user,
		group_ids=(),
		permissions=frozenset(),
		role_resource_defaults=DefaultResourceAccess(),
	)


def _message(
	thread: Thread, parent: Message | None, mtype: MessageType, text: str
) -> Message:
	message_cls = Message.__mapper__.polymorphic_map[mtype].class_
	return message_cls(
		thread_id=thread.id,
		parent_id=parent.id if parent is not None else None,
		content=[{"type": "text", "text": text}],
	)


def _anchor_id(hit: SearchHit) -> str | None:
	return str(hit.anchor.id) if hit.anchor is not None else None


@pytest.mark.asyncio
async def test_e2e_dense_search_finds_message_content_with_anchor(
	db_session: AsyncSession,
	real_vectorstore: None,
) -> None:
	owner = _user(f"ds_{_uid()}")
	db_session.add(owner)
	await db_session.flush()
	target = Thread(owner_id=owner.id, title="infra debugging", is_temporary=False)
	decoy = Thread(owner_id=owner.id, title="cake recipes", is_temporary=False)
	db_session.add_all([target, decoy])
	await db_session.flush()
	m1 = _message(
		target, None, MessageType.USER, "the api dies under load, connections pile up"
	)
	db_session.add(m1)
	await db_session.flush()
	m2 = _message(
		target,
		m1,
		MessageType.ASSISTANT,
		"postgres connection pool exhaustion - put pgbouncer in front",
	)
	db_session.add(m2)
	await db_session.flush()
	target.current_message_id = m2.id
	d1 = _message(decoy, None, MessageType.USER, "chocolate sponge with vanilla cream")
	db_session.add(d1)
	await db_session.flush()
	decoy.current_message_id = d1.id
	await db_session.commit()

	await reconcile_one_thread(target.id, db_session)
	await reconcile_one_thread(decoy.id, db_session)
	await db_session.commit()

	results = await search_threads(
		"postgres connection pool exhaustion pgbouncer",
		db_session,
		principal=_principal(owner),
		limit=5,
		search_params=_DENSE,
	)
	assert results
	assert str(results[0].item.id) == str(target.id)
	assert _anchor_id(results[0].hit) in (str(m1.id), str(m2.id))
	matched = results[0].hit.matched_chunks
	assert isinstance(matched, list) and matched


@pytest.mark.asyncio
async def test_e2e_branch_semantics_are_query_time_only(
	db_session: AsyncSession,
	real_vectorstore: None,
) -> None:
	"""switching branches changes results with zero re-vectorization."""
	owner = _user(f"br_{_uid()}")
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="storage chat", is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	m1 = _message(thread, None, MessageType.USER, "which storage engine should we use")
	db_session.add(m1)
	await db_session.flush()
	m2a = _message(
		thread, m1, MessageType.ASSISTANT, "postgres replication quorum writes zebra"
	)
	db_session.add(m2a)
	await db_session.flush()
	m2b = _message(
		thread, m1, MessageType.ASSISTANT, "redis clustering hash slots quokka"
	)
	db_session.add(m2b)
	await db_session.flush()
	thread.current_message_id = m2b.id
	await db_session.commit()

	# index the whole tree exactly once
	first = await reconcile_one_thread(thread.id, db_session)
	await db_session.commit()
	assert isinstance(first.get("built"), int) and first["built"] >= 3

	principal = _principal(owner)
	query_a = "postgres replication quorum zebra"

	# head = m2b: the m2a passage is off-branch; its text must not anchor
	head_b = await _hybrid_search_threads(
		query_a, db_session, principal=principal, search_params=_DENSE
	)
	for hit in head_b:
		assert _anchor_id(hit.hit) != str(m2a.id)

	# include_all_branches surfaces the abandoned branch with its anchor
	all_branches = await _hybrid_search_threads(
		query_a,
		db_session,
		principal=principal,
		search_params=_DENSE,
		filters=ThreadSearchFilters(include_all_branches=True),
	)
	assert all_branches
	assert _anchor_id(all_branches[0].hit) == str(m2a.id)

	# switch the head to the other branch: index untouched, results flip
	thread.current_message_id = m2a.id
	await db_session.commit()
	head_a = await _hybrid_search_threads(
		query_a, db_session, principal=principal, search_params=_DENSE
	)
	assert head_a
	assert _anchor_id(head_a[0].hit) == str(m2a.id)
	second = await reconcile_one_thread(thread.id, db_session)
	assert second["built"] == 0, "branch switch must not re-embed anything"


@pytest.mark.asyncio
async def test_e2e_vector_acl_filter_blocks_other_user(
	db_session: AsyncSession,
	real_vectorstore: None,
) -> None:
	"""the qdrant-level acl prefilter hides foreign chunks before any postfilter."""
	s = _uid()
	u_a, u_b = _user(f"acl_{s}_a"), _user(f"acl_{s}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()
	thread = Thread(owner_id=u_a.id, title="private notes", is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	m1 = _message(thread, None, MessageType.USER, f"secret launch codes {s}")
	db_session.add(m1)
	await db_session.flush()
	thread.current_message_id = m1.id
	await db_session.commit()
	await reconcile_one_thread(thread.id, db_session)
	await db_session.commit()

	own = await _hybrid_search_threads(
		f"secret launch codes {s}",
		db_session,
		principal=_principal(u_a),
		search_params=_DENSE,
	)
	assert own and str(own[0].item.id) == str(thread.id)

	foreign = await _hybrid_search_threads(
		f"secret launch codes {s}",
		db_session,
		principal=_principal(u_b),
		search_params=_DENSE,
	)
	assert not foreign


@pytest.mark.asyncio
async def test_e2e_incremental_reconcile_after_append(
	db_session: AsyncSession,
	real_vectorstore: None,
) -> None:
	owner = _user(f"inc_{_uid()}")
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="incremental chat", is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	m1 = _message(thread, None, MessageType.USER, "first question about kubernetes")
	db_session.add(m1)
	await db_session.flush()
	thread.current_message_id = m1.id
	await db_session.commit()
	await reconcile_one_thread(thread.id, db_session)
	await db_session.commit()

	m2 = _message(
		thread, m1, MessageType.ASSISTANT, "helm chart values override flamingo"
	)
	db_session.add(m2)
	await db_session.flush()
	thread.current_message_id = m2.id
	await db_session.commit()

	result = await reconcile_one_thread(thread.id, db_session)
	await db_session.commit()
	built = result.get("built")
	assert isinstance(built, int) and 1 <= built <= 2, (
		"append must rebuild only the tail passage(s)"
	)

	hits = await _hybrid_search_threads(
		"helm chart values flamingo",
		db_session,
		principal=_principal(owner),
		search_params=_DENSE,
	)
	assert hits
	assert _anchor_id(hits[0].hit) in (str(m1.id), str(m2.id))
