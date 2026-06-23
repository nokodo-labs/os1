"""sanitize legacy user preferences

Revision ID: 6e1b4a9d0c2f
Revises: 5d9a2c4e7f10
Create Date: 2026-05-17 12:00:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "6e1b4a9d0c2f"
down_revision = "5d9a2c4e7f10"
branch_labels = None
depends_on = None


_ALLOWED_FIELDS: dict[str, tuple[str, ...]] = {
	"appearance": (
		"themeMode",
		"accent",
		"autoAccentColors",
		"background",
		"autoBackground",
		"staticColor",
		"bubbleTailStyle",
	),
	"account": ("bio", "birthDate", "gender"),
	"ai": (
		"defaultAgentId",
		"bio",
		"useAccountBio",
		"memoriesEnabled",
		"chatRecall",
		"customInstructions",
		"personality",
	),
	"notifications": ("enabled", "sound", "pushEnabled"),
	"privacy": (
		"saveHistory",
		"shareUsageData",
		"useLocation",
		"useDeviceContext",
		"useBatteryStatus",
	),
	"accessibility": ("hapticFeedback",),
	"advanced": ("svgLiquidGlass", "svgLiquidGlassIsland", "svgLiquidMetal"),
	"debug": ("enableDebugApps",),
	"homepage": (
		"chats",
		"reminders",
		"notes",
		"projects",
		"friends",
		"library",
		"calendar",
	),
}


def upgrade() -> None:
	"""remove legacy and unknown preference keys."""
	op.execute(_sanitize_preferences_sql())


def downgrade() -> None:
	"""no backwards data migration."""
	return None


def _sanitize_preferences_sql() -> str:
	sections = ",\n".join(
		f"\t\t('{section}'::text, ARRAY[{_sql_array_items(fields)}]::text[])"
		for section, fields in _ALLOWED_FIELDS.items()
	)
	return f"""
	CREATE OR REPLACE FUNCTION pg_temp.sanitize_user_preferences(input jsonb)
	RETURNS jsonb
	LANGUAGE plpgsql
	AS $$
	DECLARE
		prefs jsonb := CASE
			WHEN jsonb_typeof(input) = 'object' THEN input
			ELSE '{{}}'::jsonb
		END;
		result jsonb := '{{}}'::jsonb;
		section_name text;
		allowed_fields text[];
		section_value jsonb;
		next_section jsonb;
		field_name text;
	BEGIN
		FOR section_name, allowed_fields IN
			SELECT * FROM (VALUES
{sections}
			) AS allowed(section_name, allowed_fields)
		LOOP
			section_value := prefs -> section_name;
			IF jsonb_typeof(section_value) = 'object' THEN
				next_section := '{{}}'::jsonb;
				FOREACH field_name IN ARRAY allowed_fields LOOP
					IF section_value ? field_name THEN
						next_section := jsonb_set(
							next_section,
							ARRAY[field_name],
							section_value -> field_name,
							true
						);
					END IF;
				END LOOP;

				IF next_section <> '{{}}'::jsonb THEN
					result := jsonb_set(
						result,
						ARRAY[section_name],
						next_section,
						true
					);
				END IF;
			END IF;
		END LOOP;

		RETURN result;
	END;
	$$;

	UPDATE users
	SET preferences = pg_temp.sanitize_user_preferences(preferences)
	WHERE preferences IS NOT NULL;
	"""


def _sql_array_items(values: tuple[str, ...]) -> str:
	return ", ".join(f"'{value}'" for value in values)
