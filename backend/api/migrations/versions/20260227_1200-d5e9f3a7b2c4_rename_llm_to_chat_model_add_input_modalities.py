"""rename llm to chat_model, add input_modalities column

Revision ID: d5e9f3a7b2c4
Revises: c4d8e2f6a1b3
Create Date: 2026-02-27 12:00:00.000000

"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = "d5e9f3a7b2c4"
down_revision = "c4d8e2f6a1b3"
branch_labels = None
depends_on = None


# default input modalities per model type
_MODALITIES: dict[str, list[str]] = {
	"chat_model": ["text", "images"],
	"embedding": ["text"],
	"image_generation": ["text", "images"],
	"audio": ["text", "audio"],
	"video": ["text", "images", "video"],
}


def upgrade() -> None:
	# 1. rename enum value llm -> chat_model in model_type column
	op.execute("UPDATE models SET model_type = 'chat_model' WHERE model_type = 'llm'")

	# 2. add input_modalities JSONB column with a default
	op.add_column(
		"models",
		sa.Column(
			"input_modalities",
			JSONB,
			nullable=False,
			server_default='["text", "images"]',
		),
	)

	# 3. set correct defaults per model type
	for model_type, modalities in _MODALITIES.items():
		val = json.dumps(modalities)
		op.execute(
			sa.text(
				"UPDATE models SET input_modalities = "
				"cast(:val as jsonb) WHERE model_type = :mt"
			).bindparams(val=val, mt=model_type)
		)

	# 4. drop the server default now that all rows are populated
	op.alter_column("models", "input_modalities", server_default=None)


def downgrade() -> None:
	# 1. drop input_modalities column
	op.drop_column("models", "input_modalities")

	# 2. revert enum value chat_model -> llm
	op.execute("UPDATE models SET model_type = 'llm' WHERE model_type = 'chat_model'")
