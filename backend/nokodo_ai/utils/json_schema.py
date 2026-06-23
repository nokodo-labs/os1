from __future__ import annotations

from collections.abc import Callable
from inspect import Parameter, signature
from typing import (
	Annotated,
	Any,
	Literal,
	Optional,
	TypeIs,
	Union,
	get_args,
	get_origin,
	overload,
)

from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo

from ..types.json import JSONObject, JSONValue


type EnumStrategy = Literal["anyOf", "enumDescriptions", "x-enum-descriptions"]


# ----- core schema helpers -----


def schema_from_callable(
	func: Callable[..., Any],
	skip_self: bool = True,
	skip_fields: set[str] | None = None,
	skip_dunder: bool = True,
) -> JSONObject:
	"""generate JSON Schema from a callable's signature.

	skips `self` and any `__*__` parameters (context injection).
	"""
	from inspect import get_annotations

	hints = get_annotations(func, eval_str=True)
	sig = signature(func)

	fields: dict[str, Any] = {}

	for name, param in sig.parameters.items():
		if skip_self and name == "self":
			continue
		if skip_fields and name in skip_fields:
			continue
		if skip_dunder and name.startswith("__") and name.endswith("__"):
			continue
		if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
			continue

		type_hint = hints.get(name, Any)

		if param.default is Parameter.empty:
			fields[name] = (type_hint, ...)
		else:
			fields[name] = (type_hint, param.default)

	if not fields:
		return {}

	func_name = getattr(func, "__name__", "callable")
	dynamic_model = create_model(f"{func_name}_params", **fields)
	schema: JSONObject = {k: v for k, v in dynamic_model.model_json_schema().items()}
	return schema


# ----- pydantic introspection helpers -----


def find_class_definition(
	class_name: str, fields_dict: dict[str, FieldInfo]
) -> type[BaseModel] | None:
	"""find the BaseModel subclass matching class_name by recursively
	searching fields.
	"""
	for _, field in fields_dict.items():
		result = search_type_recursively(field.annotation, class_name)
		if result:
			return result
	return None


def search_type_recursively(type_obj: Any, class_name: str) -> type[BaseModel] | None:
	"""recursively search a type annotation tree for a BaseModel with the given name."""
	if type_obj is None:
		return None

	if isinstance(type_obj, FieldInfo):
		return search_type_recursively(type_obj.annotation, class_name)

	if is_matching_model(type_obj, class_name):
		return type_obj

	if is_basemodel(type_obj) and type_obj.__name__ != class_name:
		result = find_class_definition(class_name, type_obj.model_fields)
		if result:
			return result

	args = get_args(type_obj)
	if not args:
		return None

	for arg in args:
		if is_matching_model(arg, class_name):
			return arg

		result = search_type_recursively(arg, class_name)
		if result:
			return result

		if is_basemodel(arg) and arg.__name__ != class_name:
			result = find_class_definition(class_name, arg.model_fields)
			if result:
				return result

	return None


def is_matching_model(obj: object, class_name: str) -> TypeIs[type[BaseModel]]:
	"""check if obj is a BaseModel subclass with the given name."""
	return is_basemodel(obj) and obj.__name__ == class_name


def is_basemodel(obj: object) -> TypeIs[type[BaseModel]]:
	"""check if obj is a BaseModel subclass (safe against TypeError)."""
	try:
		return isinstance(obj, type) and issubclass(obj, BaseModel)
	except TypeError:
		return False


# ----- schema processing -----


def _process_enum_field(
	field_schema: JSONObject,
	model_class: type[BaseModel],
	field_path: list[str],
) -> JSONObject:
	"""expand enum field into anyOf with per-value const schemas and descriptions.

	descriptions are sourced from Annotated literal annotations on the model field.
	"""
	field = _resolve_field_from_path(model_class, field_path)
	field_name = field_path[-1]
	class_name = field_path[1]

	enum_values: list[JSONValue] = []
	if "anyOf" in field_schema:
		anyof = field_schema["anyOf"]
		if isinstance(anyof, list):
			for item in anyof:
				if isinstance(item, dict):
					if "enum" in item:
						ev = item["enum"]
						if isinstance(ev, list):
							enum_values.extend(ev)
					elif "const" in item:
						enum_values.append(item["const"])
	elif "enum" in field_schema:
		ev = field_schema["enum"]
		if isinstance(ev, list):
			enum_values.extend(ev)
	else:
		raise ValueError(
			f"field '{field_name}' in class '{class_name}' has no 'anyOf' or 'enum'.",
		)

	enum_descriptions = extract_descriptions_from_annotation(field.annotation)
	if enum_descriptions:
		for value in enum_values:
			if not isinstance(value, str) or value not in enum_descriptions:
				raise ValueError(
					f"enum value {value!r} has no description in field '{field_name}'.",
				)

	result: JSONObject = dict(field_schema)

	if "anyOf" in result:
		anyof_raw = result.pop("anyOf")
		anyof_list: list[JSONValue] = []
		if isinstance(anyof_raw, list):
			for item in anyof_raw:
				if not isinstance(item, dict) or (
					"const" not in item and "enum" not in item
				):
					anyof_list.append(item)

		if enum_values:
			if enum_descriptions:
				for value in enum_values:
					const_schema: JSONObject = {
						"const": value,
						"type": get_json_schema_type(value),
					}
					if isinstance(value, str) and value in enum_descriptions:
						const_schema["description"] = enum_descriptions[value]
					anyof_list.append(const_schema)
			else:
				json_type = validate_homogeneous_types(enum_values)
				anyof_list.append({"enum": enum_values, "type": json_type})
		result["anyOf"] = anyof_list

	elif "enum" in result:
		if enum_descriptions:
			any_of_items: list[JSONValue] = []
			for value in enum_values:
				const_schema = {
					"const": value,
					"type": get_json_schema_type(value),
				}
				if isinstance(value, str) and value in enum_descriptions:
					const_schema["description"] = enum_descriptions[value]
				any_of_items.append(const_schema)
			result.pop("enum")
			result["anyOf"] = any_of_items
		else:
			json_type = validate_homogeneous_types(enum_values)
			result["enum"] = enum_values
			result["type"] = json_type

	else:
		raise ValueError(
			f"field '{field_name}' in class '{class_name}' has no 'anyOf' or 'enum'.",
		)

	return result


def extract_descriptions_from_annotation(annotation: Any) -> dict[str, str]:
	"""extract per-value descriptions from Annotated literal union types."""
	descriptions: dict[str, str] = {}

	origin = get_origin(annotation)
	if origin is Union or origin is Optional:
		for arg in get_args(annotation):
			if arg is type(None):
				continue
			if get_origin(arg) is Annotated:
				args = get_args(arg)
				literal_type, description = args[0], args[1]
				if get_origin(literal_type) is Literal:
					literal_value = get_args(literal_type)[0]
					descriptions[literal_value] = description

	elif origin is Annotated:
		args = get_args(annotation)
		literal_type, description = args[0], args[1]
		if get_origin(literal_type) is Literal:
			literal_value = get_args(literal_type)[0]
			descriptions[literal_value] = description

	return descriptions


def _process_default_parameter(field_schema: JSONObject) -> JSONObject:
	"""move default value from the schema into the field description,
	then drop 'default'.
	"""
	result: JSONObject = dict(field_schema)
	if "default" not in result:
		return result
	default_value = result.pop("default")

	if isinstance(default_value, list):
		desc_string = f"Default value is {default_value}."
	elif default_value is None:
		desc_string = "Default value is null."
	elif isinstance(default_value, bool):
		desc_string = f"Default value is {default_value}."
	elif isinstance(default_value, (int, float)):
		desc_string = f"Default value is {default_value}."
	else:
		desc_string = f'Default value is "{default_value}".'

	existing = result.get("description")
	if isinstance(existing, str):
		if not existing.endswith("."):
			existing += "."
		result["description"] = f"{existing} {desc_string}"
	else:
		result["description"] = desc_string

	return result


def _process_example_parameter(field_schema: JSONObject) -> JSONObject:
	"""move examples from the schema into the field description,
	then drop 'examples'.
	"""
	result: JSONObject = dict(field_schema)
	if "examples" not in result:
		return result
	examples = result.pop("examples")

	if not isinstance(examples, list):
		raise ValueError("'examples' must be a list.")

	if len(examples) == 1:
		example_str = f"Example value: {examples[0]}."
	else:
		example_str = "Example values: " + ", ".join(str(ex) for ex in examples) + "."

	existing = result.get("description")
	if isinstance(existing, str):
		if not existing.endswith("."):
			existing += "."
		result["description"] = f"{existing} {example_str}"
	else:
		result["description"] = example_str

	return result


def _process_array_constraints(field_schema: JSONObject) -> JSONObject:
	"""move array constraint keywords into the description, then drop them.

	handles minItems, maxItems, uniqueItems - keywords unsupported by some
	providers (e.g. anthropic structured output) but whose semantics must
	be preserved in natural language.
	"""
	result: JSONObject = dict(field_schema)

	parts: list[str] = []

	min_items = result.pop("minItems", None)
	if isinstance(min_items, int):
		parts.append(f"Minimum {min_items} items.")

	max_items = result.pop("maxItems", None)
	if isinstance(max_items, int):
		parts.append(f"Maximum {max_items} items.")

	unique = result.pop("uniqueItems", None)
	if unique is True:
		parts.append("All items must be unique.")

	if not parts:
		return result

	constraint_text = " ".join(parts)
	existing = result.get("description")
	if isinstance(existing, str):
		if not existing.endswith("."):
			existing += "."
		result["description"] = f"{existing} {constraint_text}"
	else:
		result["description"] = constraint_text

	return result


def process_schema(
	schema_obj: JSONValue,
	model_class: type[BaseModel] | None = None,
	make_all_required: bool = True,
	set_additionalproperties_field: bool = True,
	process_defaults: bool = True,
	process_examples: bool = True,
	process_enums: bool = True,
	enum_description_strategy: EnumStrategy = "anyOf",
	process_array_constraints: bool = False,
	_current_path: list[str] | None = None,
) -> JSONValue:
	"""recursively process a JSON schema with configurable transformations:

	- make all properties required on object nodes
	- set additionalProperties: false on object nodes
	- move defaults into descriptions
	- move examples into descriptions
	- expand enum fields with per-value descriptions
	- move array constraints (minItems/maxItems/uniqueItems) into descriptions
	"""
	if _current_path is None:
		_current_path = []

	if not any(
		[
			make_all_required,
			set_additionalproperties_field,
			process_defaults,
			process_examples,
			process_enums,
			process_array_constraints,
		]
	):
		return schema_obj

	if not isinstance(schema_obj, dict):
		return schema_obj

	result: JSONObject = dict(schema_obj)

	if "$defs" in result and isinstance(result["$defs"], dict):
		defs_dict = result["$defs"]
		assert isinstance(defs_dict, dict)
		for def_name, def_schema in defs_dict.items():
			def_path = _current_path + ["$defs", def_name]
			defs_dict[def_name] = process_schema(
				def_schema,
				model_class=model_class,
				make_all_required=make_all_required,
				set_additionalproperties_field=set_additionalproperties_field,
				process_defaults=process_defaults,
				process_examples=process_examples,
				process_enums=process_enums,
				enum_description_strategy=enum_description_strategy,
				process_array_constraints=process_array_constraints,
				_current_path=def_path,
			)

	if process_defaults and "default" in result:
		result = _process_default_parameter(result)

	if process_examples and "examples" in result:
		result = _process_example_parameter(result)

	if process_array_constraints and result.get("type") == "array":
		result = _process_array_constraints(result)

	if process_enums and ("enum" in result or "anyOf" in result):
		is_array = len(_current_path) > 1 and _current_path[-1] == "items"
		if not is_array:
			if model_class is None:
				raise ValueError(
					"model_class must be provided when processing enum fields."
				)
			if enum_description_strategy == "enumDescriptions":
				result = _process_enum_field_with_description_array(
					field_schema=result,
					model_class=model_class,
					field_path=_current_path,
					strategy=enum_description_strategy,
				)
			elif enum_description_strategy == "x-enum-descriptions":
				result = _process_enum_field_with_description_array(
					field_schema=result,
					model_class=model_class,
					field_path=_current_path,
					strategy=enum_description_strategy,
				)
			elif enum_description_strategy == "anyOf":
				result = _process_enum_field(
					field_schema=result,
					model_class=model_class,
					field_path=_current_path,
				)
			else:
				raise ValueError(
					f"unknown enum description strategy: {enum_description_strategy!r}"
				)

	if result.get("type") == "object":
		props_val = result.get("properties")
		if make_all_required and isinstance(props_val, dict):
			required_keys: list[JSONValue] = list(props_val.keys())
			result["required"] = required_keys
		if set_additionalproperties_field:
			result["additionalProperties"] = False

	if "properties" in result and isinstance(result["properties"], dict):
		props_dict = result["properties"]
		assert isinstance(props_dict, dict)
		for prop_name, prop_schema in list(props_dict.items()):
			prop_path = _current_path + ["properties", prop_name]
			props_dict[prop_name] = process_schema(
				prop_schema,
				model_class=model_class,
				make_all_required=make_all_required,
				set_additionalproperties_field=set_additionalproperties_field,
				process_defaults=process_defaults,
				process_examples=process_examples,
				process_enums=process_enums,
				enum_description_strategy=enum_description_strategy,
				process_array_constraints=process_array_constraints,
				_current_path=prop_path,
			)

	for key, value in list(result.items()):
		if key not in ("properties", "$defs"):
			item_path = _current_path + [key]
			if isinstance(value, list):
				result[key] = [
					process_schema(
						item,
						model_class=model_class,
						make_all_required=make_all_required,
						set_additionalproperties_field=set_additionalproperties_field,
						process_defaults=process_defaults,
						process_examples=process_examples,
						process_enums=process_enums,
						enum_description_strategy=enum_description_strategy,
						process_array_constraints=process_array_constraints,
						_current_path=item_path + [str(i)],
					)
					for i, item in enumerate(value)
				]
			else:
				result[key] = process_schema(
					value,
					model_class=model_class,
					make_all_required=make_all_required,
					set_additionalproperties_field=set_additionalproperties_field,
					process_defaults=process_defaults,
					process_examples=process_examples,
					process_enums=process_enums,
					enum_description_strategy=enum_description_strategy,
					process_array_constraints=process_array_constraints,
					_current_path=item_path,
				)

	return result


def pydantic_model_to_json_schema(
	model_class: type[BaseModel],
	make_all_required: bool = True,
	set_additionalproperties_field: bool = True,
	process_defaults: bool = False,
	process_examples: bool = True,
	process_enums: bool = True,
	enum_description_strategy: EnumStrategy = "anyOf",
	process_array_constraints: bool = False,
) -> JSONObject:
	"""generate an enhanced JSON schema for a pydantic model.

	builds on model_json_schema() with configurable processing via
	process_schema().
	"""
	schema = model_class.model_json_schema()
	result = process_schema(
		schema,
		model_class=model_class,
		make_all_required=make_all_required,
		set_additionalproperties_field=set_additionalproperties_field,
		process_defaults=process_defaults,
		process_examples=process_examples,
		process_enums=process_enums,
		enum_description_strategy=enum_description_strategy,
		process_array_constraints=process_array_constraints,
	)
	assert isinstance(result, dict)
	return result


@overload
def _process_enum_field_with_description_array(
	field_schema: JSONObject,
	model_class: type[BaseModel],
	field_path: list[str],
	strategy: Literal["enumDescriptions"],
) -> JSONObject: ...


@overload
def _process_enum_field_with_description_array(
	field_schema: JSONObject,
	model_class: type[BaseModel],
	field_path: list[str],
	strategy: Literal["x-enum-descriptions"],
) -> JSONObject: ...


def _process_enum_field_with_description_array(
	field_schema: JSONObject,
	model_class: type[BaseModel],
	field_path: list[str],
	strategy: Literal["enumDescriptions", "x-enum-descriptions"],
) -> JSONObject:
	"""process enum fields using description arrays
	(enumDescriptions or x-enum-descriptions).
	"""
	field = _resolve_field_from_path(model_class, field_path)
	field_name = field_path[-1]
	class_name = field_path[1]

	enum_values: list[JSONValue] = []
	if "anyOf" in field_schema:
		anyof = field_schema["anyOf"]
		if isinstance(anyof, list):
			for item in anyof:
				if isinstance(item, dict):
					if "enum" in item:
						ev = item["enum"]
						if isinstance(ev, list):
							enum_values.extend(ev)
					elif "const" in item:
						enum_values.append(item["const"])
	elif "enum" in field_schema:
		ev = field_schema["enum"]
		if isinstance(ev, list):
			enum_values.extend(ev)
	else:
		raise ValueError(
			f"field '{field_name}' in class '{class_name}' has no 'anyOf' or 'enum'.",
		)

	enum_descriptions = extract_descriptions_from_annotation(field.annotation)
	if enum_descriptions:
		for value in enum_values:
			if not isinstance(value, str) or value not in enum_descriptions:
				raise ValueError(
					f"enum value {value!r} has no description in field '{field_name}'.",
				)

	result: JSONObject = dict(field_schema)

	if "anyOf" in result:
		anyof_raw = result.pop("anyOf")
		anyof_list: list[JSONValue] = []
		if isinstance(anyof_raw, list):
			for item in anyof_raw:
				if not isinstance(item, dict) or (
					"const" not in item and "enum" not in item
				):
					anyof_list.append(item)

		if enum_values:
			json_type = validate_homogeneous_types(enum_values)
			enum_obj: JSONObject = {"enum": enum_values, "type": json_type}
			if enum_descriptions:
				enum_desc_array: list[JSONValue] = [
					enum_descriptions.get(str(v), "") for v in enum_values
				]
				enum_obj[strategy] = enum_desc_array
			anyof_list.append(enum_obj)

		result["anyOf"] = anyof_list

	elif "enum" in result:
		json_type = validate_homogeneous_types(enum_values)
		result["type"] = json_type
		if enum_descriptions:
			enum_desc_array: list[JSONValue] = [
				enum_descriptions.get(str(v), "") for v in enum_values
			]
			result[strategy] = enum_desc_array

	else:
		raise ValueError(
			f"field '{field_name}' in class '{class_name}' has no 'anyOf' or 'enum'.",
		)

	return result


def get_json_schema_type(value: object) -> str:
	"""return the JSON Schema type string for a Python value.

	note: bool is checked before int since in Python bool is a subclass of int.
	raises ValueError for unsupported types.
	"""
	if isinstance(value, bool):
		return "boolean"
	if isinstance(value, str):
		return "string"
	if isinstance(value, int):
		return "integer"
	if isinstance(value, float):
		return "number"
	raise ValueError(f"unsupported value type: {type(value)}")


def validate_homogeneous_types(values: list[JSONValue]) -> str:
	"""validate all values share a JSON type and return that type string.

	raises ValueError for empty input or mixed types.
	"""
	if not values:
		raise ValueError("no values provided for enum type validation.")

	python_types = {type(value).__name__ for value in values}
	if len(python_types) > 1:
		raise ValueError(
			f"mixed types in enum values: {python_types}. "
			"only the 'anyOf' strategy supports mixed-type enums."
		)

	return get_json_schema_type(values[0])


def _resolve_field_from_path(
	model_class: type[BaseModel], field_path: list[str]
) -> FieldInfo:
	"""resolve a FieldInfo from a model class and schema path (handles $defs)."""
	class_name = field_path[1]
	fields = model_class.model_fields

	if len(field_path) > 1 and field_path[0] == "$defs":
		class_def = find_class_definition(class_name=class_name, fields_dict=fields)
		if class_def is None:
			raise ValueError(f"class '{class_name}' not found in model fields.")
		fields = class_def.model_fields

	field_name = field_path[-1]
	try:
		return fields[field_name]
	except KeyError:
		try:
			return next(
				f for f in fields.values() if f.serialization_alias == field_name
			)
		except StopIteration:
			raise ValueError(
				f"field '{field_name}' not found in class '{class_name}'.",
			)
