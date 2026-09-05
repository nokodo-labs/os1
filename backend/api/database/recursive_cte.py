"""PostgreSQL-native cycle safety for recursive CTEs."""

from sqlalchemy import ColumnElement, literal_column, select
from sqlalchemy.sql.selectable import CTE


_CYCLE_COLUMN = "_cycle_detected"
_CYCLE_PATH_COLUMN = "_cycle_path"


def cycle_safe_cte(cte: CTE, key_columns: list[str], name: str) -> CTE:
	"""hide cycle rows and PostgreSQL's implicit cycle-tracking columns."""
	cycle_keys = ", ".join(key_columns)
	cycled = cte.suffix_with(
		f"CYCLE {cycle_keys} SET {_CYCLE_COLUMN} USING {_CYCLE_PATH_COLUMN}",
		dialect="postgresql",
	)
	columns: list[ColumnElement[object]] = [
		cycled.c[column_name] for column_name in cycled.c.keys()
	]
	return (
		select(*columns)
		.where(literal_column(f"{cycled.name}.{_CYCLE_COLUMN}").is_(False))
		.cte(name)
	)
