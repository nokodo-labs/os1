/** run steering transport helpers. */

import { api } from '$lib/api/client'
import type { RunInput } from '$lib/api/streaming'
import type { ApiMessage, SteeringState } from './types'

export type { SteeringState }

export function getMessageSteeringState(message: Pick<ApiMessage, 'metadata_'>): SteeringState | null {
	const meta = (message.metadata_ ?? {}) as Record<string, unknown>
	const state = meta.steering_state
	if (state === 'queued' || state === 'injected' || state === 'dropped') return state
	return null
}

export function getMessageSteeringRunId(message: Pick<ApiMessage, 'metadata_'>): string | null {
	const meta = (message.metadata_ ?? {}) as Record<string, unknown>
	return typeof meta.run_id === 'string' ? meta.run_id : null
}

function errorMessage(error: unknown, fallback: string): string {
	if (typeof error === 'object' && error !== null && 'detail' in error) {
		return String((error as { detail: unknown }).detail)
	}
	return fallback
}

export async function steerRun(
	runId: string,
	input: RunInput,
	parentId: string | null
): Promise<{ messageId: string; state: 'queued' | 'dropped' }> {
	const { data, error } = await api.POST('/v1/runs/{run_id}/steer', {
		params: { path: { run_id: runId } },
		body: {
			input,
			parent_id: parentId,
		},
	})
	if (error || !data) {
		throw new Error(errorMessage(error, 'failed to steer run'))
	}
	return { messageId: data.message_id, state: data.state }
}

export async function dropSteering(runId: string, messageId: string): Promise<void> {
	const { error } = await api.DELETE('/v1/runs/{run_id}/steer/{message_id}', {
		params: {
			path: { run_id: runId, message_id: messageId },
		},
	})
	if (error) {
		throw new Error(errorMessage(error, 'failed to drop steering message'))
	}
}
