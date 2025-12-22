from __future__ import annotations


type JSONValue = (
	None | bool | int | float | str | dict[str, JSONValue] | list[JSONValue]
)
type JSONObject = dict[str, JSONValue]
type JSONArray = list[JSONValue]
