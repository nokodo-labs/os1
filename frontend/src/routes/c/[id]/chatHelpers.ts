/**
 * Pure utility functions for chat page - no reactive state, no side effects.
 */

import type { components } from '$lib/api/types'

export type ApiMessage = components['schemas']['Message']

/**
 * Convert message content parts to plain text.
 */
export function contentPartsToText(parts: ApiMessage['content']): string {
	if (!parts || parts.length === 0) return ''
	return parts
		.map((part): string | null => {
			if (!part) return null
			if (part.type === 'text') {
				return 'text' in part && typeof part.text === 'string' ? part.text : null
			}
			if (part.type === 'refusal') {
				return 'reason' in part && typeof part.reason === 'string' ? part.reason : null
			}
			if (part.type === 'json') {
				try {
					return 'data' in part ? JSON.stringify(part.data) : ''
				} catch {
					return null
				}
			}
			return null
		})
		.filter((v): v is string => v !== null)
		.join('\n')
}

/**
 * Convert SDK message parts to plain text (used during streaming).
 */
export function sdkPartsToText(parts: unknown): string {
	if (!Array.isArray(parts)) return ''
	return parts
		.map((p): string | null => {
			if (!p || typeof p !== 'object') return null
			const part = p as Record<string, unknown>
			const type = typeof part.type === 'string' ? part.type : ''
			if (type === 'text' && typeof part.text === 'string') return part.text
			if (type === 'refusal' && typeof part.reason === 'string') return part.reason
			if (type === 'json' && part.data != null) {
				try {
					return JSON.stringify(part.data)
				} catch {
					return null
				}
			}
			return null
		})
		.filter((v): v is string => v !== null)
		.join('\n')
}

/**
 * Extract run_id from message metadata, or generate a legacy fallback.
 */
export function getRunId(msg: Pick<ApiMessage, 'metadata_' | 'id'>): string {
	const runId =
		msg.metadata_ && typeof msg.metadata_.run_id === 'string' ? msg.metadata_.run_id : null
	return runId ?? `legacy-${msg.id}`
}

/**
 * Parse message created_at to Date.
 */
export function getMessageCreatedAt(msg: ApiMessage): Date {
	return msg.created_at ? new Date(msg.created_at) : new Date(0)
}

/**
 * Buffer distance for auto-scroll detection.
 */
export const AUTO_SCROLL_BUFFER_PX = 50

/**
 * Check if scroll container is at bottom (within buffer).
 */
export function computeIsAtBottom(element: HTMLElement): boolean {
	return element.scrollHeight - element.scrollTop <= element.clientHeight + AUTO_SCROLL_BUFFER_PX
}
