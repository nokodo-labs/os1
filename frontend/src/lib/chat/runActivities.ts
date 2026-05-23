/**
 * message-anchored run activity event parsing and state reduction.
 *
 * run activities belong to an agent run, while message_id is the timeline
 * anchor that places them inside the chat. this module keeps replayed database
 * events and live websocket events on the same reducer path.
 */

import type {
	RunActivityEvent,
	RunActivityOutcome,
	RunActivityPhase,
	RunActivityState,
} from './types'

export const RUN_ACTIVITY_EVENT_PREFIX = 'run.activity.'

interface RawRunActivityEvent {
	id: string
	type: string
	data: Record<string, unknown>
	created_at?: string
	message_id?: string
}

/** return a non-empty string value from raw event data. */
function stringValue(value: unknown): string | null {
	return typeof value === 'string' && value.length > 0 ? value : null
}

/** return a finite number value from raw event data. */
function numberValue(value: unknown): number | undefined {
	return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

/** parse an ISO timestamp from raw event data. */
function dateValue(value: unknown): Date | undefined {
	if (typeof value !== 'string' || !value) return undefined
	const date = new Date(value)
	return Number.isNaN(date.getTime()) ? undefined : date
}

/** derive the run activity lifecycle phase from the event type. */
function phaseFromType(type: string): RunActivityPhase | null {
	if (type === 'run.activity.started') return 'started'
	if (type === 'run.activity.progress') return 'progress'
	if (type === 'run.activity.ended') return 'ended'
	return null
}

/** read a supported terminal outcome from event data. */
function outcomeFromData(value: unknown): RunActivityOutcome | null {
	if (value === 'success' || value === 'error' || value === 'cancelled') return value
	return null
}

/** build the stable reducer key for one run activity instance. */
export function runActivityKey(event: Pick<RunActivityEvent, 'activityId'>): string {
	return event.activityId
}

/** parse a raw API event into a typed run activity event, if it is one. */
export function parseRunActivityEvent(input: RawRunActivityEvent): RunActivityEvent | null {
	if (!input.type.startsWith(RUN_ACTIVITY_EVENT_PREFIX)) return null
	const data = input.data
	const phase = phaseFromType(input.type)
	if (!phase) return null
	const messageId = stringValue(input.message_id)
	const runId = stringValue(data.run_id)
	const activityId = stringValue(data.activity_id)
	const activityType = stringValue(data.activity_type)
	if (!messageId || !runId || !activityId || !activityType) return null
	let status: RunActivityEvent['status'] = 'running'
	let outcome: RunActivityOutcome | undefined
	if (phase === 'ended') {
		const endedOutcome = outcomeFromData(data.outcome)
		if (!endedOutcome) return null
		status = endedOutcome
		outcome = endedOutcome
	}
	const timestamp = dateValue(input.created_at) ?? new Date()
	return {
		id: input.id,
		type: input.type,
		phase,
		messageId,
		runId,
		activityId,
		activityType,
		status,
		timestamp,
		title: stringValue(data.title) ?? undefined,
		message: stringValue(data.message) ?? undefined,
		progress: numberValue(data.progress),
		outcome,
		error: stringValue(data.error) ?? undefined,
	}
}

/** merge a live or replayed run activity event into current render state. */
export function reduceRunActivityEvent(
	existing: RunActivityState | undefined,
	event: RunActivityEvent
): RunActivityState {
	const key = existing?.key ?? runActivityKey(event)
	const eventIds = existing?.eventIds.includes(event.id)
		? existing.eventIds
		: [...(existing?.eventIds ?? []), event.id]
	return {
		key,
		id: existing?.id ?? event.id,
		eventIds,
		messageId: event.messageId,
		runId: event.runId,
		activityId: event.activityId,
		activityType: event.activityType,
		status: event.status,
		startedAt:
			event.phase === 'started' ? event.timestamp : (existing?.startedAt ?? event.timestamp),
		updatedAt: event.timestamp,
		endedAt: event.phase === 'ended' ? event.timestamp : existing?.endedAt,
		title: event.title ?? existing?.title,
		message: event.message ?? existing?.message,
		progress: event.progress ?? existing?.progress,
		outcome: event.outcome ?? existing?.outcome,
		error: event.error ?? existing?.error,
	}
}
