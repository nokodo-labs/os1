/** summarizes notification and attachment reveal tool executions. */

import { readNonEmptyString } from '$lib/utils/records'
import type { ToolExecution, ToolSummary } from '../types'
import { getToolSummaryState } from './summaryState'

/** summarizes send notification progress and completion. */
export function summarizeSendNotification(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const title = readNonEmptyString(args.title)
	if (isFailed) return { title: 'could not send notification' }
	if (isActive) return { title: 'sending notification' }
	return { title: title ? `sent ${title}` : 'sent notification' }
}

/** summarizes attachment reveal progress and completion. */
export function summarizeRevealAttachment(execution: ToolExecution): ToolSummary {
	const { isActive, isFailed } = getToolSummaryState(execution)
	if (isFailed) return { title: 'could not show attachment' }
	if (isActive) return { title: 'showing attachment' }
	return { title: 'showed attachment' }
}
