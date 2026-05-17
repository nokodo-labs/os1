/** run steering transport helpers. */

import { api } from '$lib/api/client'
import type { RunInput } from '$lib/api/streaming'
import type { ApiMessage, SteeringState } from './types'

export type { SteeringState }

export class SteeringRunNotFoundError extends Error {
	runId: string

	constructor(runId: string, message = 'run not found') {
		super(message)
		this.name = 'SteeringRunNotFoundError'
		this.runId = runId
	}
}

export function getMessageSteeringState(
	message: Pick<ApiMessage, 'metadata_'>
): SteeringState | null {
	const meta = (message.metadata_ ?? {}) as Record<string, unknown>
	const state = meta.steering_state
	if (state === 'queued' || state === 'injected' || state === 'dropped') return state
	return null
}

export function getMessageSteeringRunId(message: Pick<ApiMessage, 'metadata_'>): string | null {
	const meta = (message.metadata_ ?? {}) as Record<string, unknown>
	return typeof meta.run_id === 'string' ? meta.run_id : null
}

export function getMessageClientSteeringId(message: Pick<ApiMessage, 'metadata_'>): string | null {
	const meta = (message.metadata_ ?? {}) as Record<string, unknown>
	return typeof meta.client_steering_id === 'string' ? meta.client_steering_id : null
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
	parentId: string | null,
	clientSteeringId: string
): Promise<{ messageId: string; state: 'queued' | 'dropped' }> {
	const { data, error } = await api.POST('/v1/runs/{run_id}/steer', {
		params: { path: { run_id: runId } },
		body: {
			input,
			parent_id: parentId,
			client_steering_id: clientSteeringId,
		},
	})
	if (error || !data) {
		const message = errorMessage(error, 'failed to steer run')
		if (message.toLowerCase().includes('run not found')) {
			throw new SteeringRunNotFoundError(runId, message)
		}
		throw new Error(message)
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
