"""thread summary purpose and default email discovery off

Revision ID: a7b8c9d2e4f5
Revises: e1f2a3b4c5d6
Create Date: 2026-05-24 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "a7b8c9d2e4f5"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


_DEFAULT_AGENT_FILTER_IDS = (
	"chat_context",
	"attachments",
	"citation_index",
	"context_compaction",
	"file_resolve",
)


def _quoted_default_agent_filter_ids() -> str:
	return ", ".join(f"'{plugin_id}'" for plugin_id in _DEFAULT_AGENT_FILTER_IDS)


def upgrade() -> None:
	# -- thread summary purpose --
	op.add_column(
		"thread_summaries",
		sa.Column(
			"purpose",
			sa.String(length=30),
			nullable=False,
			server_default="catalog",
		),
	)
	op.create_index(
		"ix_thread_summaries_purpose",
		"thread_summaries",
		["purpose"],
	)
	op.alter_column(
		"thread_summaries",
		"purpose",
		server_default="agent_context",
		existing_type=sa.String(length=30),
		existing_nullable=False,
	)
	op.drop_column("thread_summaries", "type")
	op.execute(
		"""
		WITH defaults(plugin_id, sort_order) AS (
			VALUES
				('chat_context', 1000000),
				('attachments', 1000001),
				('citation_index', 1000002),
				('context_compaction', 1000003),
				('file_resolve', 1000004)
		)
		UPDATE agents AS agent
		SET plugin_ids = COALESCE(
			(
				SELECT jsonb_agg(to_jsonb(plugin_id) ORDER BY sort_order)
				FROM (
					SELECT plugin_id, min(sort_order) AS sort_order
					FROM (
						SELECT defaults.plugin_id, defaults.sort_order
						FROM defaults
						UNION ALL
						SELECT
							CASE existing.plugin_id
								WHEN 'context_windowing' THEN 'context_compaction'
								WHEN 'context_compression' THEN 'context_compaction'
								WHEN 'attachment_decay' THEN 'attachments'
								ELSE existing.plugin_id
							END AS plugin_id,
							1000 + existing.ordinality::integer AS sort_order
						FROM jsonb_array_elements_text(
							COALESCE(agent.plugin_ids, '[]'::jsonb)
						) WITH ORDINALITY AS existing(plugin_id, ordinality)
						-- file_resolve is forced last via defaults;
						-- drop obsolete/absorbed plugin ids entirely.
						WHERE existing.plugin_id NOT IN (
							'tool_result_truncation',
							'reveal_attachment',
							'file_resolve'
						)
					) combined
					GROUP BY plugin_id
				) deduped
			),
			'[]'::jsonb
		)
		"""
	)
	op.execute(
		"""
		UPDATE settings_documents
		SET data = CASE
			WHEN data ? 'context_compaction' THEN data - 'windowing'
			ELSE jsonb_set(
				data - 'windowing',
				'{context_compaction}',
				data->'windowing'
			)
		END
		WHERE namespace = 'ai' AND data ? 'windowing'
		"""
	)
	op.execute(
		"""
		UPDATE settings_documents
		SET data = jsonb_set(
			data,
			'{context_compaction}',
			(data->'context_compaction') - 'hard_ratio' - 'summary_batch_size'
		)
		WHERE namespace = 'ai' AND data ? 'context_compaction'
		"""
	)
	# -- attachment decay settings are measured in iterations, not turns --
	op.execute(
		"""
		UPDATE settings_documents
		SET data = jsonb_set(
			data,
			'{attachments}',
			(
				(data->'attachments')
				- 'image_decay_turns'
				- 'audio_decay_turns'
				- 'video_decay_turns'
				- 'reveal_decay_turns'
			)
			|| jsonb_strip_nulls(jsonb_build_object(
				'image_decay_iterations', data->'attachments'->'image_decay_turns',
				'audio_decay_iterations', data->'attachments'->'audio_decay_turns',
				'video_decay_iterations', data->'attachments'->'video_decay_turns'
			))
		)
		WHERE namespace = 'ai' AND data ? 'attachments'
		"""
	)

	# -- default email discovery off --
	op.alter_column(
		"users",
		"find_by_email",
		existing_type=sa.Boolean(),
		existing_nullable=False,
		server_default=sa.text("false"),
	)


def downgrade() -> None:
	# -- revert attachment decay setting key names --
	op.execute(
		"""
		UPDATE settings_documents
		SET data = jsonb_set(
			data,
			'{attachments}',
			(
				(data->'attachments')
				- 'image_decay_iterations'
				- 'audio_decay_iterations'
				- 'video_decay_iterations'
			)
			|| jsonb_strip_nulls(jsonb_build_object(
				'image_decay_turns', data->'attachments'->'image_decay_iterations',
				'audio_decay_turns', data->'attachments'->'audio_decay_iterations',
				'video_decay_turns', data->'attachments'->'video_decay_iterations'
			))
		)
		WHERE namespace = 'ai' AND data ? 'attachments'
		"""
	)

	# -- revert email discovery --
	op.alter_column(
		"users",
		"find_by_email",
		existing_type=sa.Boolean(),
		existing_nullable=False,
		server_default=sa.text("true"),
	)

	# -- revert thread summary purpose --
	op.execute(
		f"""
		UPDATE agents AS agent
		SET plugin_ids = COALESCE(
			(
				SELECT jsonb_agg(
					to_jsonb(existing.plugin_id) ORDER BY existing.ordinality
				)
				FROM jsonb_array_elements_text(
					COALESCE(agent.plugin_ids, '[]'::jsonb)
				) WITH ORDINALITY AS existing(plugin_id, ordinality)
				WHERE existing.plugin_id NOT IN ({_quoted_default_agent_filter_ids()})
			),
			'[]'::jsonb
		)
		"""
	)
	op.execute(
		"""
		UPDATE settings_documents
		SET data = CASE
			WHEN data ? 'windowing' THEN data - 'context_compaction'
			ELSE jsonb_set(
				data - 'context_compaction',
				'{windowing}',
				data->'context_compaction'
			)
		END
		WHERE namespace = 'ai' AND data ? 'context_compaction'
		"""
	)
	op.add_column(
		"thread_summaries",
		sa.Column(
			"type",
			sa.String(length=20),
			nullable=False,
			server_default="window",
		),
	)
	op.drop_index("ix_thread_summaries_purpose", table_name="thread_summaries")
	op.drop_column("thread_summaries", "purpose")
