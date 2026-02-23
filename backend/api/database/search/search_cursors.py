"""cursor-based pagination helpers for search results."""

import base64
import json
from datetime import datetime
from typing import Any

from api.schemas.search import CursorPage, SearchResultItem


def encode_cursor(sort_val: Any, id_: str) -> str:
	"""encode a (sort_val, id) pair into a base64 cursor string."""
	if isinstance(sort_val, datetime):
		sort_val = sort_val.isoformat()
	payload = {"s": sort_val, "i": id_}
	raw = json.dumps(payload).encode()
	return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[Any, str]:
	"""decode a cursor string back to (sort_val, id)."""
	payload = json.loads(base64.urlsafe_b64decode(cursor))
	sort_val = payload["s"]
	# attempt to parse datetime if it looks like one
	if isinstance(sort_val, str):
		try:
			sort_val = datetime.fromisoformat(sort_val)
		except ValueError:
			pass
	return sort_val, payload["i"]


def build_cursor_page(
	items: list[SearchResultItem],
	limit: int,
	sort_key: str = "updated_at",
) -> CursorPage[SearchResultItem]:
	"""build a cursor page from items sorted by sort_key desc."""
	has_more = len(items) > limit
	page_items = items[:limit]
	next_cursor = None
	if has_more and page_items:
		last = page_items[-1]
		sort_val = getattr(last, sort_key)
		next_cursor = encode_cursor(sort_val, str(last.id))
	return CursorPage(
		items=page_items,
		next_cursor=next_cursor,
		has_more=has_more,
	)
