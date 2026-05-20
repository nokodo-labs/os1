/** summarizes note read, search, and write tool executions. */

import { notes } from '$lib/stores/notes.svelte'
import { readNonEmptyString, readNumberField, readStringField } from '$lib/utils/records'
import type { ToolExecution, ToolSummary } from '../types'
import { countTitle, getToolSummaryState, parseToolOutput } from './summaryState'

/** summarizes note search, list, and direct read executions. */
export function summarizeNoteGet(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const noteId = readNonEmptyString(args.note_id)
	if (isFailed) return { title: 'could not read note' }

	if (noteId) {
		const label = notes.get(noteId)?.title
		if (isActive) return { title: label ? `reading ${label}` : 'reading note' }
		const output = parseToolOutput(execution)
		const title = readStringField(output, 'title') ?? label
		return {
			title: title ? `read ${title}` : 'read note',
			resourceId: noteId,
			resourceType: 'note',
		}
	}

	const query = readNonEmptyString(args.query)
	if (isActive) return { title: 'searching notes', subtitle: query ?? undefined }
	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count')
	if (count !== null) {
		return {
			title: countTitle(count, 'note', 'notes', 'no notes found'),
			subtitle: query ?? undefined,
		}
	}
	return { title: 'searched notes', subtitle: query ?? undefined }
}

/** summarizes note create, update, and delete executions. */
export function summarizeNoteWrite(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const noteId = readNonEmptyString(args.note_id)
	const noteTitle = readNonEmptyString(args.title)
	const isUpdate = noteId !== null
	const label = noteTitle ?? (noteId ? (notes.get(noteId)?.title ?? null) : null)

	if (isFailed) return { title: 'could not write note' }
	if (isActive) {
		const verb = isUpdate ? 'updating' : 'creating'
		return { title: label ? `${verb} ${label}` : `${verb} note` }
	}

	const output = parseToolOutput(execution)
	const resultId = readStringField(output, 'id')
	const doneVerb = isUpdate ? 'updated' : 'created'
	return {
		title: label ? `${doneVerb} ${label}` : `${doneVerb} note`,
		resourceId: resultId ?? noteId ?? undefined,
		resourceType: 'note',
	}
}
