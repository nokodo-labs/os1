"""wipe all open-webui-imported resources from local dev environment.

deletes from:
- postgresql: threads (+ cascades to messages, participants, summaries,
  thread_projects, access_rules), files, memories, notes, projects
  where metadata->>'imported_from' = 'open_webui'
- qdrant: all vector points whose resource_id matches a deleted resource
- local storage: actual bytes on disk for files with storage_backend='local'

usage:
    uv run tools/wipe-owui-imports.py [--db-url URL] [--qdrant-url URL]
                                      [--storage-root PATH] [--dry-run]

defaults match the docker-compose.local.yml values for local dev:
    db      postgresql://nokodo-ai-admin:nokodo-ai@localhost:5432/nokodo-ai-dev
    qdrant  http://localhost:6333
    storage backend/data/uploads  (the default LocalStorageBackend root)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path


def _step(label: str) -> "tuple[str, float]":
    print(f"  {label} ...", end="", flush=True)
    return label, time.monotonic()


def _done(start: float, count: int | None = None) -> None:
    elapsed = time.monotonic() - start
    suffix = f" ({count} rows)" if count is not None else ""
    print(f" done{suffix} [{elapsed:.1f}s]")


async def _main(
    db_url: str,
    qdrant_url: str,
    storage_root: Path,
    dry_run: bool,
) -> None:
    try:
        import psycopg
    except ImportError:
        print("psycopg not available - run inside the backend venv", file=sys.stderr)
        sys.exit(1)
    try:
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.http.models import FieldCondition, Filter, MatchAny
    except ImportError:
        print(
            "qdrant-client not available - run inside the backend venv", file=sys.stderr
        )
        sys.exit(1)

    tag = "[dry-run] " if dry_run else ""

    # --- collect resource info from postgres ---
    print("connecting to postgres ...")
    # psycopg uses a slightly different url scheme; strip the +psycopg suffix if present
    pg_url = db_url.replace("postgresql+psycopg://", "postgresql://")

    async with await psycopg.AsyncConnection.connect(pg_url, autocommit=True) as conn:
        # files: need storage info before we delete
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, storage_backend, storage_key
                FROM files
                WHERE metadata->>'imported_from' = 'open_webui'

                """
            )
            file_rows = await cur.fetchall()

        file_ids = [r[0] for r in file_rows]
        local_keys = [r[2] for r in file_rows if r[1] == "local" and r[2]]
        print(f"  files to delete: {len(file_ids)}")

        # threads
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id FROM threads
                WHERE metadata->>'imported_from' = 'open_webui'

                """
            )
            thread_ids = [r[0] for r in await cur.fetchall()]
        print(f"  threads to delete: {len(thread_ids)}")

        # memories
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id FROM memories
                WHERE metadata->>'imported_from' = 'open_webui'
                """
            )
            memory_ids = [r[0] for r in await cur.fetchall()]
        print(f"  memories to delete: {len(memory_ids)}")

        # notes
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id FROM notes
                WHERE metadata->>'imported_from' = 'open_webui'

                """
            )
            note_ids = [r[0] for r in await cur.fetchall()]
        print(f"  notes to delete: {len(note_ids)}")

        # projects (folders)
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id FROM projects
                WHERE metadata->>'imported_from' = 'open_webui'

                """
            )
            project_ids = [r[0] for r in await cur.fetchall()]
        print(f"  projects to delete: {len(project_ids)}")

        all_resource_ids = file_ids + thread_ids + memory_ids + note_ids + project_ids
        print(f"  total resource ids: {len(all_resource_ids)}")

        if not all_resource_ids:
            print("nothing to delete.")
            return

        # --- qdrant cleanup ---
        print(f"\n{tag}cleaning qdrant ...")
        qdrant = AsyncQdrantClient(url=qdrant_url)
        try:
            collections_resp = await qdrant.get_collections()
            collection_names = [c.name for c in collections_resp.collections]
            print(f"  found collections: {collection_names}")
            # batch in groups of 500 to stay within qdrant filter limits
            batch_size = 500
            for coll in collection_names:
                deleted_total = 0
                for i in range(0, len(all_resource_ids), batch_size):
                    batch = all_resource_ids[i : i + batch_size]
                    if not dry_run:
                        result = await qdrant.delete(
                            collection_name=coll,
                            points_selector=Filter(
                                must=[
                                    FieldCondition(
                                        key="resource_id",
                                        match=MatchAny(any=batch),
                                    )
                                ]
                            ),
                        )
                        _ = result
                    deleted_total += len(batch)
                print(f"  {tag}{coll}: processed {deleted_total} resource ids")
        finally:
            await qdrant.close()

        # --- db deletes ---
        # delete in explicit order to avoid cascade overhead:
        # 1. null out SET NULL fk references that point INTO messages/threads
        # 2. delete messages directly (avoids self-referential cascade storm)
        # 3. delete threads (now just rows, no children left)
        # 4. delete remaining resources
        OWUI_THREAD_IDS = """
            SELECT id FROM threads WHERE metadata->>'imported_from' = 'open_webui'
        """
        OWUI_MSG_IDS = f"""
            SELECT id FROM messages WHERE thread_id IN ({OWUI_THREAD_IDS})
        """
        print(f"\n{tag}deleting from postgres ...")
        async with conn.cursor() as cur:
            if not dry_run:
                # step 1: null SET NULL fk columns that reference messages
                _, t = _step("nulling thread_participants.last_read_message_id")
                await cur.execute(
                    f"UPDATE thread_participants SET last_read_message_id = NULL"
                    f" WHERE thread_id IN ({OWUI_THREAD_IDS})"
                )
                _done(t, cur.rowcount)

                _, t = _step("nulling thread_summaries fk refs")
                await cur.execute(
                    f"UPDATE thread_summaries"
                    f" SET start_message_id = NULL, end_message_id = NULL, superseded_by_id = NULL"
                    f" WHERE thread_id IN ({OWUI_THREAD_IDS})"
                )
                _done(t, cur.rowcount)

                _, t = _step("nulling files.message_id")
                await cur.execute(
                    f"UPDATE files SET message_id = NULL"
                    f" WHERE message_id IN ({OWUI_MSG_IDS})"
                )
                _done(t, cur.rowcount)

                # null self-referential parent_id on messages so there's no
                # recursive cascade when we bulk-delete them below
                _, t = _step("nulling messages.parent_id")
                await cur.execute(
                    f"UPDATE messages SET parent_id = NULL"
                    f" WHERE thread_id IN ({OWUI_THREAD_IDS})"
                )
                _done(t, cur.rowcount)

                # memories.source_message_id: null before deleting messages
                # so the FK cascade does an index lookup instead of a seqscan.
                _, t = _step("nulling memories.source_message_id")
                await cur.execute(
                    f"UPDATE memories SET source_message_id = NULL"
                    f" WHERE source_message_id IN ({OWUI_MSG_IDS})"
                )
                _done(t, cur.rowcount)

                # threads.current_message_id and spawned_from_message_id are
                # SET NULL FK refs from messages. even though indexed, each of
                # the 63k message deletes triggers a per-row index lookup.
                # batch-null them here so the cascade fires 0 writes.
                _, t = _step("nulling threads message refs")
                await cur.execute(
                    f"UPDATE threads"
                    f" SET current_message_id = NULL, spawned_from_message_id = NULL"
                    f" WHERE id IN ({OWUI_THREAD_IDS})"
                )
                _done(t, cur.rowcount)

                # step 2: delete events for these threads BEFORE messages
                # (events.thread_id is indexed; events.message_id cascade
                # would otherwise fire per deleted message).
                _, t = _step("deleting events")
                await cur.execute(
                    f"DELETE FROM events WHERE thread_id IN ({OWUI_THREAD_IDS})"
                )
                _done(t, cur.rowcount)

                # step 3: delete messages with FK triggers disabled for this
                # session — all referencing FKs have been pre-cleaned above,
                # so skipping trigger evaluation is safe and avoids index
                # overhead proportional to the message count.
                _, t = _step("deleting messages")
                await cur.execute("SET session_replication_role = replica")
                await cur.execute(
                    f"DELETE FROM messages WHERE thread_id IN ({OWUI_THREAD_IDS})"
                )
                _done(t, cur.rowcount)
                await cur.execute("RESET session_replication_role")

                # step 4: delete threads (participants/summaries cascade but are now empty)
                _, t = _step("deleting threads")
                await cur.execute(
                    "DELETE FROM threads WHERE metadata->>'imported_from' = 'open_webui'"
                )
                _done(t, cur.rowcount)

                # step 5: remaining resources
                _, t = _step("deleting files")
                await cur.execute(
                    "DELETE FROM files WHERE metadata->>'imported_from' = 'open_webui'"
                )
                _done(t, cur.rowcount)

                _, t = _step("deleting memories")
                await cur.execute(
                    "DELETE FROM memories WHERE metadata->>'imported_from' = 'open_webui'"
                )
                _done(t, cur.rowcount)

                _, t = _step("deleting notes")
                await cur.execute(
                    "DELETE FROM notes WHERE metadata->>'imported_from' = 'open_webui'"
                )
                _done(t, cur.rowcount)

                _, t = _step("deleting projects")
                await cur.execute(
                    "DELETE FROM projects WHERE metadata->>'imported_from' = 'open_webui'"
                )
                _done(t, cur.rowcount)
            else:
                print(f"  [dry-run] would delete {len(thread_ids)} threads")
                print(f"  [dry-run] would delete {len(file_ids)} files")
                print(f"  [dry-run] would delete {len(memory_ids)} memories")
                print(f"  [dry-run] would delete {len(note_ids)} notes")
                print(f"  [dry-run] would delete {len(project_ids)} projects")

    # --- local storage cleanup ---
    if local_keys:
        print(f"\n{tag}cleaning local storage under {storage_root} ...")
        deleted_files = 0
        missing_files = 0
        for key in local_keys:
            path = storage_root / key
            meta_path = path.with_suffix(path.suffix + ".meta")
            if path.exists():
                if not dry_run:
                    path.unlink()
                    if meta_path.exists():
                        meta_path.unlink()
                deleted_files += 1
            else:
                missing_files += 1
        print(f"  {tag}deleted {deleted_files} files ({missing_files} already missing)")
    else:
        print("\nno local storage files to clean.")

    print(f"\n{tag}done.")


def main() -> None:
    # windows: psycopg async requires SelectorEventLoop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    repo_root = Path(__file__).resolve().parent.parent
    default_storage_root = repo_root / "backend" / "data" / "uploads"

    parser = argparse.ArgumentParser(
        description="wipe open-webui-imported resources from local dev"
    )
    parser.add_argument(
        "--db-url",
        default="postgresql://nokodo-ai-admin:nokodo-ai@localhost:5432/nokodo-ai-dev",
        help="postgresql connection url",
    )
    parser.add_argument(
        "--qdrant-url",
        default="http://localhost:6333",
        help="qdrant http url",
    )
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=default_storage_root,
        help="local storage backend root path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be deleted without making any changes",
    )
    args = parser.parse_args()

    asyncio.run(
        _main(
            db_url=args.db_url,
            qdrant_url=args.qdrant_url,
            storage_root=args.storage_root,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
