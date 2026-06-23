/** shared state derivation helpers for tool summary handlers. */

import { parseJsonRecord } from '$lib/utils/records'
import type { ToolExecution, ToolStatus } from '../types'

export interface ToolSummaryState {
	args: Record<string, unknown>
	status: ToolStatus
	isActive: boolean
	isFailed: boolean
}

/** derives the common state flags every summary handler needs. */
export function getToolSummaryState(execution: ToolExecution): ToolSummaryState {
	const hasResult = execution.result != null
	return {
		args: execution.toolCall.arguments,
		status: execution.status,
		isActive: !hasResult && (execution.status === 'pending' || execution.status === 'running'),
		isFailed: execution.status === 'error' || execution.result?.isError === true,
	}
}

/** parses successful tool output as a json object record. */
export function parseToolOutput(execution: ToolExecution): Record<string, unknown> | null {
	if (!execution.result || execution.result.isError) return null
	return parseJsonRecord(execution.result.output)
}

/** formats a count result with singular, plural, and empty labels. */
export function countTitle(count: number, singular: string, plural: string, empty: string): string {
	if (count === 0) return empty
	return `found ${count} ${count === 1 ? singular : plural}`
}
