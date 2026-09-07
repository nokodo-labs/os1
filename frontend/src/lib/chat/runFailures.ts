/**
 * durable run-failure event parsing and outstanding-state derivation.
 *
 * a `run.error` is the run's final output, anchored to the message the agent
 * was answering. it arrives twice - live via fanout and again on reload from
 * the event log - so it is deduped by event id.
 */

import { getMessageAgentId } from './helpers'
import type { ApiMessage, RunFailureEntry, RunFailureReason } from './types'

export const RUN_ERROR_EVENT_TYPE = 'run.error'

interface RawRunFailureEvent {
	id: string
	type: string
	data: Record<string, unknown>
	created_at?: string
	message_id?: string
}

function stringValue(value: unknown): string | null {
	return typeof value === 'string' && value.length > 0 ? value : null
}

/**
 * anything outside the closed set is treated as a provider error, matching the
 * backend's own rule that an unrecognized reason never leaks through.
 */
function reasonValue(value: unknown): RunFailureReason {
	if (
		value === 'cancelled' ||
		value === 'provider_error' ||
		value === 'never_started' ||
		value === 'not_delivered'
	) {
		return value
	}
	return 'provider_error'
}

/** parse a `run.error` event, or null when it is not one. */
export function parseRunFailureEvent(event: RawRunFailureEvent): RunFailureEntry | null {
	if (event.type !== RUN_ERROR_EVENT_TYPE) return null

	const threadId = stringValue(event.data.thread_id)
	const agentId = stringValue(event.data.agent_id)
	if (!threadId || !agentId) return null

	const createdAt = event.created_at ? new Date(event.created_at) : new Date()

	return {
		id: event.id,
		threadId,
		agentId,
		reason: reasonValue(event.data.reason),
		runId: stringValue(event.data.run_id),
		anchorMessageId: stringValue(event.message_id),
		partialMessageId: stringValue(event.data.partial_message_id),
		createdAt: Number.isNaN(createdAt.getTime()) ? new Date() : createdAt,
	}
}

/** user-facing copy for each reason. */
export function runFailureLabel(reason: RunFailureReason): string {
	switch (reason) {
		case 'cancelled':
			return 'generation stopped'
		case 'never_started':
			return "the agent didn't start"
		case 'not_delivered':
			// a run DID exist and would not take the message, so this must not
			// be phrased as the agent never starting.
			return "your message didn't reach the agent"
		case 'provider_error':
			return "the agent couldn't respond"
	}
}

/**
 * whether a failure still stands.
 *
 * derived, never stored: a failure is stale once the same agent produced a
 * later answer on the same anchor. two failures followed by a success is real
 * history, so only the newest state matters, not the count.
 */
export function isFailureOutstanding(
	failure: RunFailureEntry,
	messages: Iterable<ApiMessage>
): boolean {
	for (const message of messages) {
		if (message.type !== 'assistant') continue
		// the agent id lives on the column OR in metadata depending on which
		// writer produced the row, so it must be read the one canonical way -
		// matching the column alone leaves every failure outstanding forever.
		if (getMessageAgentId(message) !== failure.agentId) continue
		if (message.id === failure.partialMessageId) continue
		// a retry answers the anchor STRUCTURALLY (spliced onto it); an ordinary
		// answer names it semantically. either settles the failure - matching
		// only the reply pointer leaves a retried failure outstanding forever.
		const answersAnchor =
			message.reply_to_message_id === failure.anchorMessageId ||
			message.parent_id === failure.anchorMessageId
		if (!answersAnchor) continue
		const answeredAt = message.created_at ? new Date(message.created_at) : null
		if (answeredAt && answeredAt.getTime() >= failure.createdAt.getTime()) return false
	}
	return true
}
