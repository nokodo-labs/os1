/** summarizes global resource search tool executions. */

import { readNonEmptyString, readNumberField } from '$lib/utils/records'
import type { ToolExecution, ToolSummary } from '../types'
import { countTitle, getToolSummaryState, parseToolOutput } from './summaryState'

/** summarizes all-resource search progress and result counts. */
export function summarizeResourceSearch(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const query = readNonEmptyString(args.query)
	if (isFailed) return { title: 'resource search failed', subtitle: query ?? undefined }
	if (isActive) return { title: 'searching resources', subtitle: query ?? undefined }

	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count')
	if (count !== null) {
		return {
			title: countTitle(count, 'resource', 'resources', 'no resources found'),
			subtitle: query ?? undefined,
		}
	}
	return { title: 'searched resources', subtitle: query ?? undefined }
}
