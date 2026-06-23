/** summarizes think tool executions and streamed thought titles. */

import { isRecord, readNonEmptyString, readNumberField } from '$lib/utils/records'
import type { ToolExecution, ToolSummary } from '../types'
import { getToolSummaryState, parseToolOutput } from './summaryState'

/** returns server-reported or client-measured think duration. */
export function getThinkElapsed(execution: ToolExecution): string | null {
	const output = parseToolOutput(execution)
	const elapsedSeconds = readNumberField(output, 'elapsed_seconds')
	if (elapsedSeconds !== null) return elapsedSeconds.toFixed(1)

	if (!execution.startedAt || !execution.completedAt) return null
	const ms = execution.completedAt.getTime() - execution.startedAt.getTime()
	return (ms / 1000).toFixed(1)
}

/** returns the best title from think arguments or streamed raw arguments. */
export function getThinkTitle(execution: ToolExecution): string | null {
	const title = readNonEmptyString(execution.toolCall.arguments.title)
	if (title) return title

	const thoughts = execution.toolCall.arguments.thoughts
	if (Array.isArray(thoughts)) {
		for (const thought of thoughts) {
			if (!isRecord(thought)) continue
			const summary = readNonEmptyString(thought.summary)
			if (summary) return summary
		}
	}

	return (
		extractStreamingStringField(execution.rawArguments, 'title') ??
		extractStreamingStringField(execution.rawArguments, 'summary')
	)
}

/** summarizes think tool progress and completion. */
export function summarizeThink(execution: ToolExecution): ToolSummary {
	const { status, isFailed } = getToolSummaryState(execution)
	const elapsed = getThinkElapsed(execution)
	const thinkTitle = getThinkTitle(execution)
	if (isFailed) return { title: 'thinking failed' }
	if (thinkTitle) return { title: thinkTitle }
	if (status === 'completed' && elapsed !== null) return { title: `thought for ${elapsed}s` }
	return { title: 'thinking' }
}

/** extracts a string field from partial streamed json arguments. */
function extractStreamingStringField(raw: string | undefined, field: string): string | null {
	if (!raw) return null
	const fieldPattern = field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
	const match = new RegExp(`"${fieldPattern}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)`).exec(raw)
	const encoded = match?.[1]
	if (!encoded) return null
	try {
		const decoded: unknown = JSON.parse(`"${encoded}"`)
		return readNonEmptyString(decoded)
	} catch {
		return readNonEmptyString(encoded)
	}
}
