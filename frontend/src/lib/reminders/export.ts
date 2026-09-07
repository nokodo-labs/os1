/**
 * structured export for a reminder list.
 *
 * the shape mirrors what the panel renders: pending items first, completed ones
 * filed under their own group, and sub-reminders nested under their parent
 * rather than flattened into the same array.
 */

import type { components } from '$lib/api/types'

type ApiReminder = components['schemas']['Reminder']
type ApiReminderWithSubtasks = components['schemas']['ReminderWithSubtasks']
type ApiReminderList = components['schemas']['ReminderList']
type Recurrence = components['schemas']['Recurrence']
type ReminderStatus = components['schemas']['ReminderStatus']

export type ExportableReminder = ApiReminder | ApiReminderWithSubtasks

export interface ReminderExportItem {
	id: string
	list_id: string
	parent_id: string | null
	title: string
	description: string | null
	status: ReminderStatus
	position: number
	due_at: string | null
	remind_at: string | null
	completed_at: string | null
	created_at: string
	updated_at: string
	recurrence: Recurrence | null
	recurrence_until: string | null
	subtasks: ReminderExportGroup
}

/** every level of the tree keeps completed items out of the pending list. */
export interface ReminderExportGroup {
	pending: ReminderExportItem[]
	completed: ReminderExportItem[]
}

export interface ReminderExportCounts {
	total: number
	pending: number
	completed: number
}

export interface ReminderListExportInfo {
	id: string
	name: string
	description: string | null
	color: string | null
	icon: string | null
	is_default: boolean
	owner_id: string
	created_at: string
	updated_at: string
}

export interface ReminderListExport {
	list: ReminderListExportInfo | null
	counts: ReminderExportCounts
	reminders: ReminderExportGroup
}

function subtasksOf(reminder: ExportableReminder): ExportableReminder[] {
	if (!('subtasks' in reminder)) return []
	return reminder.subtasks ?? []
}

function byPosition(items: ExportableReminder[]): ExportableReminder[] {
	return [...items].sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
}

function toExportItem(reminder: ExportableReminder): ReminderExportItem {
	return {
		id: reminder.id,
		list_id: reminder.list_id,
		parent_id: reminder.parent_id ?? null,
		title: reminder.title,
		description: reminder.description ?? null,
		status: reminder.status,
		position: reminder.position ?? 0,
		due_at: reminder.due_at ?? null,
		remind_at: reminder.remind_at ?? null,
		completed_at: reminder.completed_at ?? null,
		created_at: reminder.created_at,
		updated_at: reminder.updated_at,
		recurrence: reminder.recurrence ?? null,
		recurrence_until: reminder.recurrence_until ?? null,
		subtasks: groupRemindersForExport(subtasksOf(reminder)),
	}
}

export function groupRemindersForExport(items: ExportableReminder[]): ReminderExportGroup {
	const group: ReminderExportGroup = { pending: [], completed: [] }
	for (const reminder of byPosition(items)) {
		const item = toExportItem(reminder)
		if (item.status === 'completed') group.completed.push(item)
		else group.pending.push(item)
	}
	return group
}

export function countReminderExportGroup(group: ReminderExportGroup): ReminderExportCounts {
	let pending = 0
	let completed = 0
	const walk = (entry: ReminderExportGroup): void => {
		pending += entry.pending.length
		completed += entry.completed.length
		for (const item of [...entry.pending, ...entry.completed]) walk(item.subtasks)
	}
	walk(group)
	return { total: pending + completed, pending, completed }
}

function toListInfo(list: ApiReminderList | null): ReminderListExportInfo | null {
	if (!list) return null
	return {
		id: list.id,
		name: list.name,
		description: list.description ?? null,
		color: list.color ?? null,
		icon: list.icon ?? null,
		is_default: list.is_default,
		owner_id: list.owner_id,
		created_at: list.created_at,
		updated_at: list.updated_at,
	}
}

export function buildReminderListExport(
	list: ApiReminderList | null,
	items: ExportableReminder[]
): ReminderListExport {
	const reminders = groupRemindersForExport(items)
	return {
		list: toListInfo(list),
		counts: countReminderExportGroup(reminders),
		reminders,
	}
}

// markdown

function formatExportDate(value: string | null): string | null {
	if (!value) return null
	return new Date(value).toLocaleString().toLowerCase()
}

function appendMarkdownItem(lines: string[], item: ReminderExportItem, depth: number): void {
	const indent = '  '.repeat(depth)
	lines.push(`${indent}- [${item.status === 'completed' ? 'x' : ' '}] ${item.title}`)

	const meta = [
		formatExportDate(item.due_at) ? `due: ${formatExportDate(item.due_at)}` : null,
		formatExportDate(item.remind_at) ? `remind: ${formatExportDate(item.remind_at)}` : null,
		item.recurrence ? 'repeats' : null,
	]
		.filter(Boolean)
		.join(' | ')
	if (meta) lines.push(`${indent}  ${meta}`)

	const description = item.description?.trim()
	if (description) {
		for (const line of description.split('\n')) lines.push(`${indent}  ${line}`)
	}

	for (const subtask of [...item.subtasks.pending, ...item.subtasks.completed]) {
		appendMarkdownItem(lines, subtask, depth + 1)
	}
}

export function buildReminderListMarkdown(params: {
	title: string
	url: string
	data: ReminderListExport
}): string {
	const { title, url, data } = params
	const lines = [
		`# ${data.list?.name || title}`,
		'',
		`total: ${data.counts.total}`,
		`pending: ${data.counts.pending}`,
		`completed: ${data.counts.completed}`,
		`link: ${url}`,
	]

	if (data.reminders.pending.length > 0) {
		lines.push('', '## reminders', '')
		for (const item of data.reminders.pending) appendMarkdownItem(lines, item, 0)
	}

	if (data.reminders.completed.length > 0) {
		lines.push('', '## completed', '')
		for (const item of data.reminders.completed) appendMarkdownItem(lines, item, 0)
	}

	return lines.join('\n')
}
