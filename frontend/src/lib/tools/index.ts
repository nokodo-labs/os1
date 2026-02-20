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

// re-export the reactive tracker
export { ToolExecutionTracker } from './toolExecutionTracker.svelte'

// ============================================================================
// Core Types
// ============================================================================

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
}

/** Tool result from ToolMessage */
export interface ToolResult {
	toolCallId: string
	output: string
	isError: boolean
}

export type ToolSummary = {
	title: string
	subtitle?: string
}

// ============================================================================
// Native Tool Registry
// ============================================================================

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
		'send_notification',
		{
			displayName: 'notification',
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
		'memory_recall',
		{
			displayName: 'recall memories',
			icon: 'brain',
			inline: false,
		},
	],
	[
		'think',
		{
			displayName: 'thinking',
			icon: 'brain',
			inline: true,
		},
	],
	// add more native tools here as they're implemented
])

/** Check if a tool has native UI support */
export function isNativeTool(toolName: string): boolean {
	return nativeTools.has(toolName)
}

/** Get native tool definition if available */
export function getNativeToolDefinition(toolName: string): NativeToolDefinition | null {
	return nativeTools.get(toolName) ?? null
}

// ============================================================================
// Parsing Functions
// ============================================================================

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

	return {
		toolCallId: (message.tool_call_id as string | undefined) ?? '',
		output,
		isError: (message.is_error as boolean | undefined) ?? false,
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

// ============================================================================
// Display Helpers
// ============================================================================

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
	const isNative = isNativeTool(execution.toolCall.name)

	if (isNative && execution.toolCall.name === 'think') {
		const elapsed = getThinkElapsed(execution)
		if (execution.status === 'error') {
			return { title: 'thinking failed' }
		}
		if (execution.status === 'completed' && elapsed !== null) {
			return { title: `thought for ${elapsed}s` }
		}
		return { title: 'thinking' }
	}

	if (isNative && execution.toolCall.name === 'send_notification') {
		const def = getNativeToolDefinition('send_notification')
		const parsed = def?.parseArgs ? def.parseArgs(execution.toolCall.arguments) : null
		const title =
			parsed && typeof (parsed as Record<string, unknown>).title === 'string'
				? ((parsed as Record<string, unknown>).title as string)
				: null
		const body =
			parsed && typeof (parsed as Record<string, unknown>).body === 'string'
				? ((parsed as Record<string, unknown>).body as string)
				: null

		const stateLabel =
			execution.status === 'error'
				? 'notification failed'
				: execution.status === 'completed'
					? 'notification sent'
					: execution.status === 'running'
						? 'sending notification'
						: 'preparing notification'

		if (title && body) {
			return { title: stateLabel }
		}
		if (execution.lastMessage) return { title: stateLabel, subtitle: execution.lastMessage }
		return { title: stateLabel }
	}

	const displayName = getToolDisplayName(execution.toolCall.name)
	if (execution.lastMessage) return { title: displayName, subtitle: execution.lastMessage }
	if (execution.events.length > 0) {
		return { title: displayName, subtitle: formatToolEventLine(execution.events.at(-1)!) }
	}
	return { title: displayName }
}
