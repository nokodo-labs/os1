/** summarizes web browsing and web search tool executions. */

import { readNonEmptyString } from '$lib/utils/records'
import { safeHostname } from '$lib/utils/url'
import type { ToolExecution, ToolSummary } from '../types'
import { countWebSearchSources } from '../webSearch'
import { getToolSummaryState } from './summaryState'

/** summarizes agentic web search progress and source counts. */
export function summarizeAgenticWebSearch(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const query = readNonEmptyString(args.query)
	if (isFailed) return { title: 'web search failed' }
	if (isActive) return { title: 'searching the web', subtitle: query ?? undefined }

	const sourceCount = countWebSearchSources(execution)
	if (sourceCount !== null && sourceCount > 0) {
		return { title: `searched ${sourceCount} sources`, subtitle: query ?? undefined }
	}
	return { title: 'searched the web', subtitle: query ?? undefined }
}

/** summarizes direct URL fetch executions. */
export function summarizeFetchUrl(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const url = readNonEmptyString(args.url)
	const domain = url ? safeHostname(url) : null
	if (isFailed) return { title: domain ? `failed to open ${domain}` : 'failed to open page' }
	if (isActive) return { title: domain ? `opening ${domain}` : 'opening page' }
	return { title: domain ? `opened ${domain}` : 'opened page' }
}
