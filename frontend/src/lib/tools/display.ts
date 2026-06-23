/** display helpers for generic tool rows and event lines. */

import { getToolDisplayName } from './registry'
import type { ToolEvent, ToolStatus } from './types'
import { formatWebSearchProgressLine } from './webSearch'

/** maps tool execution status to the compact label shown in tool UI. */
export function getToolStatusLabel(status: ToolStatus): string {
	switch (status) {
		case 'pending':
			return 'waiting'
		case 'running':
			return 'running'
		case 'completed':
			return 'done'
		case 'error':
			return 'failed'
	}
}

/** formats raw tool arguments for generic fallback display. */
export function formatToolArgs(args: Record<string, unknown>): string {
	const entries = Object.entries(args)
	if (entries.length === 0) return ''

	return entries
		.map(([key, value]) => {
			const displayValue =
				typeof value === 'string'
					? value.length > 50
						? value.slice(0, 50) + '...'
						: value
					: JSON.stringify(value)
			return `${key}: ${displayValue}`
		})
		.join(', ')
}

/** formats one realtime tool event into a short progress line. */
export function formatToolEventLine(event: ToolEvent): string {
	if (event.type === 'tool.notification') {
		if (event.data.description) return event.data.description
		if (event.data.message) return event.data.message
		if (event.data.notificationCount !== undefined) {
			return `notification sent to ${event.data.notificationCount}`
		}
		return 'notification sent'
	}

	if (event.type === 'tool.progress') {
		const webSearchLine = formatWebSearchProgressLine(event)
		if (webSearchLine) return webSearchLine
		if (event.data.message) return event.data.message
		if (
			event.data.step !== undefined &&
			event.data.totalSteps !== undefined &&
			event.data.totalSteps > 0
		) {
			return `step ${event.data.step}/${event.data.totalSteps}`
		}
		if (event.data.progress !== undefined) {
			return `${Math.round(event.data.progress * 100)}%`
		}
		return 'working'
	}

	if (event.type === 'tool.custom') {
		return event.data.description ?? event.data.message ?? 'update'
	}

	return event.data.description ?? event.data.message ?? getToolDisplayName(event.toolName)
}
