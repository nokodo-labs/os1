/** shared frontend types for tool calls, events, results, and summaries. */

import type { components } from '$lib/api/types'

export type ApiMessage = components['schemas']['Message']
export type ResourceAttachment = components['schemas']['ResourceAttachment']

export interface ToolCall {
	id: string
	name: string
	arguments: Record<string, unknown> | string
}

export type ToolStatus = 'pending' | 'running' | 'completed' | 'error'

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

export interface ToolEvent {
	id: string
	type: ToolEventType
	toolCallId: string
	toolName: string
	timestamp: Date
	data: ToolEventData
}

export interface ToolExecution {
	toolCall: { id: string; name: string; arguments: Record<string, unknown> }
	status: ToolStatus
	events: ToolEvent[]
	startedAt?: Date
	completedAt?: Date
	progress?: number
	lastMessage?: string
	error?: string
	result?: ToolResult
	rawArguments?: string
}

export interface ToolResult {
	toolCallId: string
	output: string
	isError: boolean
	contentParts?: ApiMessage['content']
	/** resource refs ({type, id}) attached by the tool (producer tools). */
	attachmentRefs?: ResourceAttachment[]
	metadata?: Record<string, unknown>
}

export type ToolSummaryResourceType =
	| 'note'
	| 'reminder'
	| 'reminder_list'
	| 'file'
	| 'project'
	| 'chat'
	| 'calendar_event'

export interface ToolSummary {
	title: string
	subtitle?: string
	resourceId?: string
	resourceType?: ToolSummaryResourceType
	/** display name of the MCP server backing this tool, when applicable. */
	mcpServerName?: string
}
