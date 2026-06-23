/** summarizes code interpreter tool executions. */

import { readNonEmptyString } from '$lib/utils/records'
import type { ToolExecution, ToolSummary } from '../types'
import { getToolSummaryState } from './summaryState'

/** summarizes code execution progress and generated attachment counts. */
export function summarizeCodeInterpreter(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const actionName = readNonEmptyString(args.action_name)
	if (isFailed) return { title: actionName ? `${actionName} failed` : 'code failed' }
	if (isActive) return { title: actionName ?? 'running code' }

	const fileParts = execution.result?.contentParts?.filter(
		(part) => part.type === 'file' || part.type === 'image'
	)
	const fileCount = fileParts?.length ?? 0
	const baseTitle = actionName ?? 'ran code'
	if (fileCount > 0) {
		const label = fileCount === 1 ? '1 file' : `${fileCount} files`
		return { title: baseTitle, subtitle: `created ${label}` }
	}
	return { title: baseTitle }
}
