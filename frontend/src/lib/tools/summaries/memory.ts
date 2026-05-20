/** summarizes memory recall and creation tool executions. */

import { readNumberField } from '$lib/utils/records'
import type { ToolExecution, ToolSummary } from '../types'
import { getToolSummaryState, parseToolOutput } from './summaryState'

/** summarizes memory recall progress and result counts. */
export function summarizeMemoryRecall(execution: ToolExecution): ToolSummary {
	const { isActive, isFailed } = getToolSummaryState(execution)
	if (isFailed) return { title: 'could not recall memories' }
	if (isActive) return { title: 'recalling memories' }

	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count')
	if (count !== null) {
		if (count === 0) return { title: 'no memories found' }
		return { title: `recalled ${count} ${count === 1 ? 'memory' : 'memories'}` }
	}
	return { title: 'recalled memories' }
}

/** summarizes memory creation progress and completion. */
export function summarizeMemoryCreate(execution: ToolExecution): ToolSummary {
	const { isActive, isFailed } = getToolSummaryState(execution)
	if (isFailed) return { title: 'could not save memory' }
	if (isActive) return { title: 'creating a memory' }
	return { title: 'created a memory' }
}
