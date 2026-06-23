/** summarizes file read and edit tool executions. */

import { files } from '$lib/stores/files.svelte'
import { readNonEmptyString, readNumberField, readStringField } from '$lib/utils/records'
import type { ToolExecution, ToolSummary } from '../types'
import { countTitle, getToolSummaryState, parseToolOutput } from './summaryState'

/** summarizes file search, list, and read executions. */
export function summarizeFileGet(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const fileId = readNonEmptyString(args.file_id)
	const query = readNonEmptyString(args.query)

	if (isFailed) return { title: 'could not read file' }
	if (fileId) return summarizeFileRead(execution, fileId, isActive)
	if (isActive) {
		return query ? { title: 'searching files', subtitle: query } : { title: 'listing files' }
	}

	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count')
	if (count !== null) {
		return {
			title: countTitle(count, 'file', 'files', 'no files found'),
			subtitle: query ?? undefined,
		}
	}
	return query ? { title: 'searched files', subtitle: query } : { title: 'listed files' }
}

/** summarizes file create, update, and delete executions. */
export function summarizeFileEdit(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const fileId = readNonEmptyString(args.file_id)
	const fileName = readNonEmptyString(args.filename)
	const label = fileName ?? (fileId ? (files.get(fileId)?.filename ?? null) : null)

	if (isFailed) return { title: label ? `could not edit ${label}` : 'could not edit file' }
	if (isActive) return { title: label ? `editing ${label}` : 'editing file' }
	return {
		title: label ? `edited ${label}` : 'edited file',
		resourceId: fileId ?? undefined,
		resourceType: 'file',
	}
}

/** summarizes a direct file read execution. */
function summarizeFileRead(
	execution: ToolExecution,
	fileId: string,
	isActive: boolean
): ToolSummary {
	const label = files.get(fileId)?.filename
	if (isActive) return { title: label ? `reading ${label}` : 'reading file' }
	const output = parseToolOutput(execution)
	const filename = readStringField(output, 'filename') ?? label
	return {
		title: filename ? `read ${filename}` : 'read file',
		resourceId: fileId,
		resourceType: 'file',
	}
}
