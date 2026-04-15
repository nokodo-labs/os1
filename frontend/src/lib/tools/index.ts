/**
 * Tool call parsing system for rich UX rendering.
 *
 * This module provides a comprehensive, type-safe system for:
 * 1. Parsing tool calls from messages
 * 2. Tracking tool execution events (via reactive ToolExecutionTracker)
 * 3. Rendering appropriate UI components for different tool types
 *
 * Key concepts:
 * - Native tools: have dedicated UI components (e.g., send_notification, web_search)
 * - Generic tools: rendered with a standard expandable tool call UI
 * - Tool events: real-time progress updates from tool execution
 * - Reactive tracking: ToolExecutionTracker uses Svelte 5 $state runes for
 *   fine-grained reactivity - no manual tick counters or {#key} blocks needed.
 */

import type { components } from '$lib/api/types'
import { files } from '$lib/stores/files.svelte'
import { notes } from '$lib/stores/notes.svelte'

// re-export the reactive tracker
export { ToolExecutionTracker } from './toolExecutionTracker.svelte'

// Core Types

/** Tool call from an assistant message */
export interface ToolCall {
	id: string
	name: string
	/** Parsed object arguments, or raw string from streaming (accumulated fragments). */
	arguments: Record<string, unknown> | string
}

/** Tool execution status */
export type ToolStatus = 'pending' | 'running' | 'completed' | 'error'

/** Tool event from real-time streaming */
export interface ToolEvent {
	id: string
	type: ToolEventType
	toolCallId: string
	toolName: string
	timestamp: Date
	data: ToolEventData
}

export type ToolEventType = 'tool.progress' | 'tool.custom' | 'tool.notification'

export interface ToolEventData {
	message?: string
	progress?: number
	step?: number
	totalSteps?: number
	notificationId?: string
	notificationCount?: number
	toolCallArgs?: Record<string, unknown>
	payload?: Record<string, unknown>
	description?: string
}

/** Aggregated tool execution state */
export interface ToolExecution {
	/** Tool call with parsed arguments (always an object, never raw string). */
	toolCall: { id: string; name: string; arguments: Record<string, unknown> }
	status: ToolStatus
	events: ToolEvent[]
	startedAt?: Date
	completedAt?: Date
	progress?: number
	lastMessage?: string
	error?: string
	result?: ToolResult
	/** raw accumulated JSON string from streaming - use for partial field extraction */
	rawArguments?: string
}

/** Tool result from ToolMessage */
export interface ToolResult {
	toolCallId: string
	output: string
	isError: boolean
	/** Non-text content parts (images, files) from tool message attachments. */
	contentParts?: ApiMessage['content']
	/** Structured metadata from backend (flows via message.metadata_). */
	metadata?: Record<string, unknown>
}

export type ToolSummary = {
	title: string
	subtitle?: string
	/** resource ID extracted from tool result (for widget rendering) */
	resourceId?: string
	/** type hint for the resource (note, reminder, file) */
	resourceType?: 'note' | 'reminder' | 'file'
}

// Native Tool Registry

/**
 * Registry of native tools that have dedicated UI components.
 * Each native tool specifies:
 * - component: the Svelte component to render
 * - parseArgs: function to validate/transform tool arguments
 */
export interface NativeToolDefinition<TArgs = Record<string, unknown>> {
	/** Display name for the tool */
	displayName: string
	/** Icon identifier (optional) */
	icon?: string
	/** Whether this tool should be rendered inline in the message flow */
	inline?: boolean
	/** Parse and validate tool arguments */
	parseArgs?: (args: Record<string, unknown>) => TArgs | null
}

const nativeTools = new Map<string, NativeToolDefinition>([
	[
		'think',
		{
			displayName: 'thinking',
			icon: 'brain',
			inline: true,
		},
	],
	[
		'agentic_web_search',
		{
			displayName: 'web search',
			icon: 'globe',
			inline: true,
		},
	],
	[
		'fetch_url',
		{
			displayName: 'browse page',
			icon: 'globe',
			inline: true,
		},
	],
	[
		'memory_recall',
		{
			displayName: 'recall memories',
			icon: 'brain',
			inline: true,
		},
	],
	[
		'memory_create',
		{
			displayName: 'save memory',
			icon: 'brain',
			inline: true,
		},
	],
	[
		'note_get',
		{
			displayName: 'read note',
			icon: 'note',
			inline: true,
		},
	],
	[
		'note_write',
		{
			displayName: 'write note',
			icon: 'note',
			inline: true,
		},
	],
	[
		'reminder_get',
		{
			displayName: 'check reminders',
			icon: 'bell',
			inline: true,
		},
	],
	[
		'reminder_write',
		{
			displayName: 'set reminder',
			icon: 'bell',
			inline: true,
		},
	],
	[
		'file_get',
		{
			displayName: 'read file',
			icon: 'document',
			inline: true,
		},
	],
	[
		'file_edit',
		{
			displayName: 'edit file',
			icon: 'pencil',
			inline: true,
		},
	],
	[
		'generate_image',
		{
			displayName: 'create image',
			icon: 'photo',
			inline: true,
		},
	],
	[
		'generate_video',
		{
			displayName: 'create video',
			icon: 'film',
			inline: true,
		},
	],
	[
		'generate_audio',
		{
			displayName: 'create audio',
			icon: 'headphone',
			inline: true,
		},
	],
	[
		'code_interpreter',
		{
			displayName: 'run code',
			icon: 'terminal',
			inline: true,
		},
	],
	[
		'send_notification',
		{
			displayName: 'send notification',
			icon: 'bell',
			inline: true,
			parseArgs: (args: Record<string, unknown>) => {
				const title = typeof args.title === 'string' ? args.title : null
				const body = typeof args.body === 'string' ? args.body : null
				const userId = typeof args.user_id === 'string' ? args.user_id : null
				if (!title || !body) return null
				return userId ? { title, body, user_id: userId } : { title, body }
			},
		},
	],
	[
		'reveal_attachment',
		{
			displayName: 'show attachment',
			icon: 'eye',
			inline: true,
		},
	],
])

/** Check if a tool has native UI support */
export function isNativeTool(toolName: string): boolean {
	return nativeTools.has(toolName)
}

/** Get native tool definition if available */
export function getNativeToolDefinition(toolName: string): NativeToolDefinition | null {
	return nativeTools.get(toolName) ?? null
}

// Parsing Functions

type ApiMessage = components['schemas']['Message']

/**
 * Parse tool calls from an assistant message.
 */
export function parseToolCalls(message: ApiMessage): ToolCall[] {
	if (message.type !== 'assistant') return []
	const toolCalls = message.tool_calls ?? []

	return toolCalls.map((tc) => ({
		id: String(tc.id ?? ''),
		name: String(tc.name ?? ''),
		arguments: parseToolArguments(tc.arguments),
	}))
}

/**
 * Parse tool arguments from string or object.
 */
function parseToolArguments(args: unknown): Record<string, unknown> {
	if (!args) return {}
	if (typeof args === 'object' && args !== null) {
		return args as Record<string, unknown>
	}
	if (typeof args === 'string') {
		try {
			const parsed = JSON.parse(args)
			if (typeof parsed === 'object' && parsed !== null) {
				return parsed as Record<string, unknown>
			}
		} catch {
			// ignore parse errors
		}
	}
	return {}
}

/**
 * Parse tool result from a tool message.
 */
export function parseToolResult(message: ApiMessage): ToolResult | null {
	if (message.type !== 'tool') return null

	const content = message.content ?? []
	const textPart = content.find((p) => p?.type === 'text')
	const output = textPart && 'text' in textPart ? (textPart.text ?? '') : ''

	// extract non-text content parts (images, files) for attachment rendering
	const attachmentParts = content.filter((p) => p && p.type !== 'text')

	return {
		toolCallId: (message.tool_call_id as string | undefined) ?? '',
		output,
		isError: (message.is_error as boolean | undefined) ?? false,
		contentParts: attachmentParts.length > 0 ? attachmentParts : undefined,
		metadata: (message.metadata_ ?? undefined) as Record<string, unknown> | undefined,
	}
}

/**
 * Check if a message is purely tool-related and shouldn't be rendered directly.
 * Messages that only contain tool calls (no text content) should be hidden.
 */
export function isToolOnlyMessage(message: ApiMessage): boolean {
	if (message.type === 'tool') return true

	if (message.type === 'assistant') {
		const hasToolCalls = (message.tool_calls?.length ?? 0) > 0
		const hasTextContent = (message.content ?? []).some(
			(p) => p?.type === 'text' && p.text?.trim()
		)
		return hasToolCalls && !hasTextContent
	}

	return false
}

/**
 * Parse a stream event into a ToolEvent.
 */
export function parseToolEvent(event: {
	id?: string
	type: string
	data?: Record<string, unknown>
	created_at?: string
	message_id?: string
}): ToolEvent | null {
	const validTypes: ToolEventType[] = ['tool.progress', 'tool.custom', 'tool.notification']

	if (!validTypes.includes(event.type as ToolEventType)) return null
	const eventId = typeof event.id === 'string' ? event.id : null
	if (!eventId) return null

	const data = event.data ?? {}

	const toolCallArgs: Record<string, unknown> = {}
	if (event.type === 'tool.notification') {
		const title = typeof data.title === 'string' ? data.title : null
		const body = typeof data.body === 'string' ? data.body : null
		const userId = typeof data.target_user_id === 'string' ? data.target_user_id : null
		if (title) toolCallArgs.title = title
		if (body) toolCallArgs.body = body
		if (userId) toolCallArgs.user_id = userId
	}

	return {
		id: eventId,
		type: event.type as ToolEventType,
		toolCallId: (data.tool_call_id as string) ?? '',
		toolName: (data.tool_name as string) ?? '',
		timestamp: event.created_at ? new Date(event.created_at) : new Date(),
		data: {
			message: data.message as string | undefined,
			progress: data.progress as number | undefined,
			step: data.step as number | undefined,
			totalSteps: data.total_steps as number | undefined,
			notificationId: data.notification_id as string | undefined,
			notificationCount: data.notification_count as number | undefined,
			toolCallArgs: Object.keys(toolCallArgs).length > 0 ? toolCallArgs : undefined,
			payload: data.payload as Record<string, unknown> | undefined,
			description: data.description as string | undefined,
		},
	}
}

// Display Helpers

/** Get a human-readable display name for a tool */
export function getToolDisplayName(toolName: string): string {
	const native = getNativeToolDefinition(toolName)
	if (native) return native.displayName

	// convert snake_case to readable format
	return toolName.replace(/_/g, ' ')
}

/** Get a status label for tool execution */
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

/** Format tool arguments for display */
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

	return event.data.description ?? event.data.message ?? 'update'
}

/** Get the elapsed time in seconds for a think tool execution from server JSON response */
export function getThinkElapsed(execution: ToolExecution): string | null {
	// prefer server-reported elapsed time from JSON response
	if (execution.result && !execution.result.isError) {
		try {
			const parsed = JSON.parse(execution.result.output)
			if (typeof parsed.elapsed_seconds === 'number') {
				return parsed.elapsed_seconds.toFixed(1)
			}
		} catch {
			// not json, fall through
		}
	}
	// fallback to client-side timing
	if (!execution.startedAt || !execution.completedAt) return null
	const ms = execution.completedAt.getTime() - execution.startedAt.getTime()
	return (ms / 1000).toFixed(1)
}

export function getToolSummary(execution: ToolExecution): ToolSummary {
	const name = execution.toolCall.name
	const args = execution.toolCall.arguments
	const status = execution.status
	// if a result exists, the tool is definitively done regardless of status
	const hasResult = execution.result != null
	const isActive = !hasResult && (status === 'pending' || status === 'running')
	const isFailed = status === 'error' || (hasResult && execution.result!.isError)

	switch (name) {
		case 'think': {
			const elapsed = getThinkElapsed(execution)
			if (isFailed) return { title: 'thinking failed' }
			if (status === 'completed' && elapsed !== null) {
				return { title: `thought for ${elapsed}s` }
			}
			return { title: 'thinking' }
		}

		case 'agentic_web_search': {
			const query = typeof args.query === 'string' ? args.query : null
			if (isFailed) return { title: 'web search failed' }
			if (isActive) return { title: 'searching the web', subtitle: query ?? undefined }
			// count sources from events or result
			const sourceCount = countWebSearchSources(execution)
			if (sourceCount !== null && sourceCount > 0) {
				return { title: `searched ${sourceCount} sources`, subtitle: query ?? undefined }
			}
			return { title: 'searched the web', subtitle: query ?? undefined }
		}

		case 'fetch_url': {
			const url = typeof args.url === 'string' ? args.url : null
			const domain = url ? safeHostname(url) : null
			if (isFailed)
				return { title: domain ? `failed to open ${domain}` : 'failed to open page' }
			if (isActive) return { title: domain ? `opening ${domain}` : 'opening page' }
			return { title: domain ? `opened ${domain}` : 'opened page' }
		}

		case 'memory_recall': {
			if (isFailed) return { title: 'could not recall memories' }
			if (isActive) return { title: 'recalling memories' }
			const output = parseToolOutput(execution)
			const count = typeof output?.count === 'number' ? output.count : null
			if (count !== null) {
				if (count === 0) return { title: 'no memories found' }
				return { title: `recalled ${count} ${count === 1 ? 'memory' : 'memories'}` }
			}
			return { title: 'recalled memories' }
		}

		case 'memory_create': {
			if (isFailed) return { title: 'could not save memory' }
			if (isActive) return { title: 'creating a memory' }
			return { title: 'created a memory' }
		}

		case 'note_get': {
			const noteId = typeof args.note_id === 'string' ? args.note_id : null
			if (isFailed) return { title: 'could not read note' }
			if (noteId) {
				const cached = notes.get(noteId)
				const label = cached?.title
				if (isActive) return { title: label ? `reading "${label}"` : 'reading note' }
				const output = parseToolOutput(execution)
				const title = (output?.title as string) ?? label
				return {
					title: title ? `read "${title}"` : 'read note',
					resourceId: noteId,
					resourceType: 'note',
				}
			}
			const query = typeof args.query === 'string' ? args.query : null
			if (isActive) return { title: 'searching notes', subtitle: query ?? undefined }
			const output = parseToolOutput(execution)
			const count = typeof output?.count === 'number' ? output.count : null
			if (count !== null) {
				if (count === 0) return { title: 'no notes found', subtitle: query ?? undefined }
				return {
					title: `found ${count} ${count === 1 ? 'note' : 'notes'}`,
					subtitle: query ?? undefined,
				}
			}
			return { title: 'searched notes', subtitle: query ?? undefined }
		}

		case 'note_write': {
			const noteTitle = typeof args.title === 'string' ? args.title : null
			if (isFailed) return { title: 'could not write note' }
			const isUpdate = typeof args.note_id === 'string'
			const verb = isUpdate ? 'updating' : 'creating'
			const doneVerb = isUpdate ? 'updated' : 'created'
			const label =
				noteTitle ?? (isUpdate ? (notes.get(args.note_id as string)?.title ?? null) : null)
			if (isActive) return { title: label ? `${verb} "${label}"` : `${verb} note` }
			const output = parseToolOutput(execution)
			const resultId = output?.id as string | undefined
			return {
				title: label ? `${doneVerb} "${label}"` : `${doneVerb} note`,
				resourceId:
					resultId ?? (typeof args.note_id === 'string' ? args.note_id : undefined),
				resourceType: 'note',
			}
		}

		case 'reminder_get': {
			const remId = typeof args.reminder_id === 'string' ? args.reminder_id : null
			if (isFailed) return { title: 'could not check reminders' }
			if (remId) {
				if (isActive) return { title: 'checking reminder' }
				const output = parseToolOutput(execution)
				const title = output?.title as string | undefined
				return {
					title: title ? `checked "${title}"` : 'checked reminder',
					resourceId: remId,
					resourceType: 'reminder',
				}
			}
			const query = typeof args.query === 'string' ? args.query : null
			if (isActive) return { title: 'searching reminders', subtitle: query ?? undefined }
			const output = parseToolOutput(execution)
			const count = typeof output?.count === 'number' ? output.count : null
			if (count !== null) {
				if (count === 0)
					return { title: 'no reminders found', subtitle: query ?? undefined }
				return {
					title: `found ${count} ${count === 1 ? 'reminder' : 'reminders'}`,
					subtitle: query ?? undefined,
				}
			}
			return { title: 'searched reminders', subtitle: query ?? undefined }
		}

		case 'reminder_write': {
			const remTitle = typeof args.title === 'string' ? args.title : null
			if (isFailed) return { title: 'could not set reminder' }
			const isUpdate = typeof args.reminder_id === 'string'
			const verb = isUpdate ? 'updating' : 'creating'
			const doneVerb = isUpdate ? 'updated' : 'created'
			if (isActive) return { title: remTitle ? `${verb} "${remTitle}"` : `${verb} reminder` }
			const output = parseToolOutput(execution)
			const resultId = output?.id as string | undefined
			return {
				title: remTitle ? `${doneVerb} "${remTitle}"` : `${doneVerb} reminder`,
				resourceId:
					resultId ??
					(typeof args.reminder_id === 'string' ? args.reminder_id : undefined),
				resourceType: 'reminder',
			}
		}

		case 'file_get': {
			const fileId = typeof args.file_id === 'string' ? args.file_id : null
			if (isFailed) return { title: 'could not read file' }
			if (fileId) {
				const cached = files.get(fileId)
				const label = cached?.filename
				if (isActive) return { title: label ? `reading "${label}"` : 'reading file' }
				const output = parseToolOutput(execution)
				const filename = (output?.filename as string) ?? label
				return {
					title: filename ? `read "${filename}"` : 'read file',
					resourceId: fileId,
					resourceType: 'file',
				}
			}
			if (isActive) return { title: 'listing files' }
			const output = parseToolOutput(execution)
			const count = typeof output?.count === 'number' ? output.count : null
			if (count !== null) {
				if (count === 0) return { title: 'no files found' }
				return { title: `found ${count} ${count === 1 ? 'file' : 'files'}` }
			}
			return { title: 'listed files' }
		}

		case 'file_edit': {
			const fileId = typeof args.file_id === 'string' ? args.file_id : null
			const fileName = typeof args.filename === 'string' ? args.filename : null
			const cached = fileId ? files.get(fileId) : null
			const label = fileName ?? cached?.filename
			if (isFailed)
				return { title: label ? `could not edit "${label}"` : 'could not edit file' }
			if (isActive) return { title: label ? `editing "${label}"` : 'editing file' }
			return {
				title: label ? `edited "${label}"` : 'edited file',
				resourceId: fileId ?? undefined,
				resourceType: 'file',
			}
		}

		case 'generate_image': {
			if (isFailed) return { title: 'could not create image' }
			if (isActive) return { title: 'creating image' }
			const output = parseToolOutput(execution)
			const count = typeof output?.count === 'number' ? output.count : 1
			const action = typeof args.file_id === 'string' ? 'edited' : 'created'
			return { title: `${action} ${count} ${count === 1 ? 'image' : 'images'}` }
		}

		case 'generate_video': {
			if (isFailed) return { title: 'could not create video' }
			if (isActive) return { title: 'creating video' }
			const output = parseToolOutput(execution)
			const count = typeof output?.count === 'number' ? output.count : 1
			return { title: `created ${count} ${count === 1 ? 'video' : 'videos'}` }
		}

		case 'generate_audio': {
			if (isFailed) return { title: 'could not create audio' }
			if (isActive) return { title: 'creating audio' }
			const output = parseToolOutput(execution)
			const count = typeof output?.count === 'number' ? output.count : 1
			return { title: `created ${count} audio ${count === 1 ? 'clip' : 'clips'}` }
		}

		case 'code_interpreter': {
			const actionName = typeof args.action_name === 'string' ? args.action_name : null
			if (isFailed) return { title: actionName ? `${actionName} failed` : 'code failed' }
			if (isActive) return { title: actionName ?? 'running code' }
			// count file attachments in result
			const fileParts = execution.result?.contentParts?.filter(
				(p) => p.type === 'file' || p.type === 'image'
			)
			const fileCount = fileParts?.length ?? 0
			const baseTitle = actionName ?? 'ran code'
			if (fileCount > 0) {
				const label = fileCount === 1 ? '1 file' : `${fileCount} files`
				return { title: baseTitle, subtitle: `created ${label}` }
			}
			return { title: baseTitle }
		}

		case 'send_notification': {
			const title = typeof args.title === 'string' ? args.title : null
			if (isFailed) return { title: 'could not send notification' }
			if (isActive) return { title: 'sending notification' }
			return { title: title ? `sent "${title}"` : 'sent notification' }
		}

		case 'reveal_attachment': {
			if (isFailed) return { title: 'could not show attachment' }
			if (isActive) return { title: 'showing attachment' }
			return { title: 'showed attachment' }
		}

		default: {
			const displayName = getToolDisplayName(name)
			if (execution.lastMessage)
				return { title: displayName, subtitle: execution.lastMessage }
			if (execution.events.length > 0) {
				return {
					title: displayName,
					subtitle: formatToolEventLine(execution.events.at(-1)!),
				}
			}
			return { title: displayName }
		}
	}
}

/** safely extract hostname from a URL */
function safeHostname(url: string): string | null {
	try {
		return new URL(url).hostname.replace(/^www\./, '')
	} catch {
		return null
	}
}

/** count web search sources from events payload */
function countWebSearchSources(execution: ToolExecution): number | null {
	for (const event of execution.events) {
		const sources = event.data.payload?.sources
		if (Array.isArray(sources)) return sources.length
	}
	return null
}

/** parse the JSON output from a completed tool result */
function parseToolOutput(execution: ToolExecution): Record<string, unknown> | null {
	if (!execution.result || execution.result.isError) return null
	try {
		const parsed = JSON.parse(execution.result.output)
		if (typeof parsed === 'object' && parsed !== null) return parsed
	} catch {
		// not json
	}
	return null
}
