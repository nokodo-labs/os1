#!/bin/sh
# run migrations before the app process starts, in exactly one container.
#
# api.main imports api.settings, whose module-level Settings() reads the
# settings_documents table at IMPORT time and validates it strictly. a store
# holding data a pending migration is meant to rewrite would therefore raise
# before the in-lifespan upgrade ever runs. a separate process, with only the
# alembic env imported, has no such dependency.
#
# every service shares this image, so the upgrade is gated on RUN_MIGRATIONS:
# exactly one service sets it and the rest wait on that service. running the
# upgrade concurrently in three containers would race on the version table.
#
# the in-lifespan upgrade stays as an idempotent safety net.
set -e

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
	# mirror BootSettings.coerce_bool's truthy set and init_db's target
	# selection. this is the primary migration runner now, so disagreeing with
	# init_db about BRANCHING_MIGRATIONS would take the whole stack down on a
	# setting meant to make deployment more permissive.
	migration_target=head
	case "$(printf '%s' "${BRANCHING_MIGRATIONS:-}" | tr '[:upper:]' '[:lower:]')" in
	1 | true | yes | on) migration_target=heads ;;
	esac
	alembic -c api/migrations/alembic.ini upgrade "${migration_target}"
fi

exec "$@"
