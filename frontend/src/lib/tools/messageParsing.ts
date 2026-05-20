/** parses persisted and streamed tool messages into frontend tool state. */

import { isRecord, parseJsonRecord, readNonEmptyString } from '$lib/utils/records'
import type { ApiMessage, ToolCall, ToolEvent, ToolEventType, ToolResult } from './types'

/** extracts assistant tool calls with parsed argument objects. */
export function parseToolCalls(message: ApiMessage): ToolCall[] {
	if (message.type !== 'assistant') return []
	const toolCalls = message.tool_calls ?? []

	return toolCalls.map((toolCall) => ({
		id: String(toolCall.id ?? ''),
		name: String(toolCall.name ?? ''),
		arguments: parseToolArguments(toolCall.arguments),
	}))
}

/** normalizes raw tool-call arguments into a record for the tracker. */
function parseToolArguments(args: unknown): Record<string, unknown> {
	if (isRecord(args)) return args
	if (typeof args === 'string') return parseJsonRecord(args) ?? {}
	return {}
}

/** extracts a tool result from a persisted tool message. */
export function parseToolResult(message: ApiMessage): ToolResult | null {
	if (message.type !== 'tool') return null
	const metadata = isRecord(message.metadata_) ? message.metadata_ : undefined
	const metadataToolCallId = readNonEmptyString(metadata?.tool_call_id)
	const toolCallId = readNonEmptyString(message.tool_call_id) ?? metadataToolCallId
	if (!toolCallId) return null

	const content = message.content ?? []
	const textPart = content.find((part) => part?.type === 'text')
	const output = textPart && 'text' in textPart ? (textPart.text ?? '') : ''
	const attachmentParts = content.filter((part) => part && part.type !== 'text')

	return {
		toolCallId,
		output,
		isError: message.is_error ?? false,
		contentParts: attachmentParts.length > 0 ? attachmentParts : undefined,
		metadata,
	}
}

/** returns true when a message should be hidden because it only carries tool data. */
export function isToolOnlyMessage(message: ApiMessage): boolean {
	if (message.type === 'tool') return true

	if (message.type === 'assistant') {
		const hasToolCalls = (message.tool_calls?.length ?? 0) > 0
		const hasTextContent = (message.content ?? []).some(
			(part) => part?.type === 'text' && part.text?.trim()
		)
		return hasToolCalls && !hasTextContent
	}

	return false
}

/** parses realtime tool progress, custom, and notification events. */
export function parseToolEvent(event: {
	id?: string
	type: string
	data?: Record<string, unknown>
	created_at?: string
	message_id?: string
}): ToolEvent | null {
	const validTypes: ToolEventType[] = ['tool.progress', 'tool.custom', 'tool.notification']
	const eventType = validTypes.find((validType) => validType === event.type)
	const eventId = readNonEmptyString(event.id)
	if (!eventType || !eventId) return null

	const data = event.data ?? {}
	const toolCallArgs: Record<string, unknown> = {}
	if (eventType === 'tool.notification') {
		const title = readNonEmptyString(data.title)
		const body = readNonEmptyString(data.body)
		const userId = readNonEmptyString(data.target_user_id)
		if (title) toolCallArgs.title = title
		if (body) toolCallArgs.body = body
		if (userId) toolCallArgs.user_id = userId
	}

	return {
		id: eventId,
		type: eventType,
		toolCallId: readNonEmptyString(data.tool_call_id) ?? '',
		toolName: readNonEmptyString(data.tool_name) ?? '',
		timestamp: event.created_at ? new Date(event.created_at) : new Date(),
		data: {
			message: readNonEmptyString(data.message) ?? undefined,
			progress: typeof data.progress === 'number' ? data.progress : undefined,
			step: typeof data.step === 'number' ? data.step : undefined,
			totalSteps: typeof data.total_steps === 'number' ? data.total_steps : undefined,
			notificationId: readNonEmptyString(data.notification_id) ?? undefined,
			notificationCount:
				typeof data.notification_count === 'number' ? data.notification_count : undefined,
			toolCallArgs: Object.keys(toolCallArgs).length > 0 ? toolCallArgs : undefined,
			payload: isRecord(data.payload) ? data.payload : undefined,
			description: readNonEmptyString(data.description) ?? undefined,
		},
	}
}
