import type { components } from '$lib/api/types'
import { contentPartsToText } from '$lib/chat/helpers'
import { calendars } from '$lib/stores/calendars.svelte'
import { chat } from '$lib/stores/chat.svelte'
import { files } from '$lib/stores/files.svelte'
import { groups } from '$lib/stores/groups.svelte'
import type { ResourceAccessPayload } from '$lib/stores/modals.svelte'
import { notes } from '$lib/stores/notes.svelte'
import { projects } from '$lib/stores/projects.svelte'
import { reminders } from '$lib/stores/reminders.svelte'
import type { ExportFormat } from './resourceAccessModal'

type ApiFile = components['schemas']['File']
type ApiMessage = components['schemas']['Message']
type ApiReminder = components['schemas']['Reminder']
type ApiReminderWithSubtasks = components['schemas']['ReminderWithSubtasks']
type ApiThread = components['schemas']['Thread']
type ReminderSnapshotItem = ApiReminder | ApiReminderWithSubtasks

export type ResourceSnapshot = {
	markdown: string
	json: Record<string, unknown>
}

export type ResourceSnapshotRequest = {
	payload: ResourceAccessPayload | null
	title: string
	url: string
	threadMessageLimit?: number
}

const DEFAULT_THREAD_MESSAGE_LIMIT = 500

export function cleanSnapshotFilename(value: string): string {
	return (
		value
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/(^-|-$)/g, '') || 'share'
	)
}

export function snapshotExtension(format: ExportFormat): string {
	return format === 'json' ? 'json' : format
}

export function snapshotMimeType(format: ExportFormat): string {
	if (format === 'json') return 'application/json;charset=utf-8'
	if (format === 'txt') return 'text/plain;charset=utf-8'
	return 'text/markdown;charset=utf-8'
}

export function plainTextFromMarkdown(markdown: string): string {
	return markdown
		.replace(/^#{1,6}\s+/gm, '')
		.replace(/^[-*]\s+/gm, '- ')
		.trim()
}

export function exportResourceSnapshot(snapshot: ResourceSnapshot, format: ExportFormat): string {
	if (format === 'md') return snapshot.markdown
	if (format === 'txt') return plainTextFromMarkdown(snapshot.markdown)
	return JSON.stringify(snapshot.json, null, 2)
}

function threadTitle(thread: ApiThread | null, fallback: string): string {
	return thread?.title?.trim() || fallback
}

function messageText(message: ApiMessage): string {
	return contentPartsToText(message.content).trim()
}

function formatSnapshotDate(value: string | null | undefined): string | null {
	if (!value) return null
	return new Date(value).toLocaleString().toLowerCase()
}

function reminderSubtasks(reminder: ReminderSnapshotItem): ReminderSnapshotItem[] {
	if (!('subtasks' in reminder)) return []
	return reminder.subtasks ?? []
}

function reminderJson(reminder: ReminderSnapshotItem): Record<string, unknown> {
	return {
		...reminder,
		subtasks: reminderSubtasks(reminder).map(reminderJson),
	}
}

function appendReminderSnapshot(lines: string[], reminder: ReminderSnapshotItem, depth = 0): void {
	const indent = '  '.repeat(depth)
	const checked = reminder.status === 'completed' ? 'x' : ' '
	lines.push(`${indent}- [${checked}] ${reminder.title}`)
	const dueAt = formatSnapshotDate(reminder.due_at)
	const remindAt = formatSnapshotDate(reminder.remind_at)

	const meta = [
		dueAt ? `due: ${dueAt}` : null,
		remindAt ? `remind: ${remindAt}` : null,
		reminder.recurrence ? 'repeats' : null,
	]
		.filter(Boolean)
		.join(' | ')
	if (meta) lines.push(`${indent}  ${meta}`)

	const description = reminder.description?.trim()
	if (description) {
		for (const line of description.split('\n')) {
			lines.push(`${indent}  ${line}`)
		}
	}

	for (const subtask of reminderSubtasks(reminder)) {
		appendReminderSnapshot(lines, subtask, depth + 1)
	}
}

function makeSnapshot(
	payload: ResourceAccessPayload | null,
	title: string,
	url: string,
	markdown: string,
	data: Record<string, unknown>
): ResourceSnapshot {
	return {
		markdown,
		json: {
			resource_type: payload?.resourceType ?? null,
			resource_id: payload?.resourceId ?? null,
			title,
			url,
			exported_at: new Date().toISOString(),
			...data,
		},
	}
}

export async function buildResourceSnapshot({
	payload,
	title,
	url,
	threadMessageLimit = DEFAULT_THREAD_MESSAGE_LIMIT,
}: ResourceSnapshotRequest): Promise<ResourceSnapshot> {
	if (!payload) return makeSnapshot(payload, title, url, url, {})
	switch (payload.resourceType) {
		case 'thread': {
			const thread = await chat.threadCache.getThread(payload.resourceId)
			const { messages } = await chat.threadCache.getMessages(
				payload.resourceId,
				0,
				threadMessageLimit
			)
			const lines = [`# ${threadTitle(thread, title)}`, '', `link: ${url}`, '']
			for (const message of messages) {
				const text = messageText(message)
				if (!text) continue
				lines.push(`## ${message.type}`, '', text, '')
			}
			return makeSnapshot(payload, title, url, lines.join('\n'), {
				thread: thread ? { ...thread } : null,
				messages: messages.map((message) => ({
					...message,
					text: messageText(message),
				})),
				message_count: messages.length,
				truncated: messages.length >= threadMessageLimit,
			})
		}
		case 'note': {
			await notes.load()
			const note = notes.get(payload.resourceId)
			const markdown = [
				`# ${note?.title || title}`,
				'',
				note?.content ?? '',
				'',
				`link: ${url}`,
			]
				.filter(Boolean)
				.join('\n')
			return makeSnapshot(payload, title, url, markdown, { note: note ? { ...note } : null })
		}
		case 'file': {
			await files.load()
			const file = files.get(payload.resourceId) as ApiFile | null
			const markdown = [
				`# ${file?.filename || title}`,
				'',
				file?.mime_type ? `type: ${file.mime_type}` : '',
				file?.size_bytes ? `size: ${file.size_bytes} bytes` : '',
				`link: ${url}`,
			]
				.filter(Boolean)
				.join('\n')
			return makeSnapshot(payload, title, url, markdown, { file: file ? { ...file } : null })
		}
		case 'project': {
			await projects.load()
			const project = projects.getById(payload.resourceId)
			const markdown = [
				`# ${project?.name || title}`,
				'',
				project?.description ?? '',
				'',
				`link: ${url}`,
			]
				.filter(Boolean)
				.join('\n')
			return makeSnapshot(payload, title, url, markdown, {
				project: project ? { ...project } : null,
			})
		}
		case 'group': {
			await groups.load()
			const group = groups.getById(payload.resourceId)
			const markdown = [
				`# ${group?.name || title}`,
				'',
				group?.description ?? '',
				'',
				`link: ${url}`,
			]
				.filter(Boolean)
				.join('\n')
			return makeSnapshot(payload, title, url, markdown, {
				group: group ? { ...group } : null,
			})
		}
		case 'reminder_list': {
			await reminders.loadLists()
			const list = reminders.getListById(payload.resourceId)
			const listReminders = await reminders.loadReminders(payload.resourceId, {
				force: true,
			})
			const lines = [
				`# ${list?.name || title}`,
				'',
				list ? `total: ${list.total_count}` : '',
				list ? `pending: ${list.pending_count}` : '',
				list ? `completed: ${list.completed_count}` : '',
				`link: ${url}`,
			].filter(Boolean)
			if (listReminders.length > 0) {
				lines.push('', '## reminders', '')
				for (const reminder of listReminders) appendReminderSnapshot(lines, reminder)
			}
			return makeSnapshot(payload, title, url, lines.join('\n'), {
				list: list ? { ...list } : null,
				counts: list
					? {
							total: list.total_count,
							pending: list.pending_count,
							completed: list.completed_count,
						}
					: null,
				reminders: listReminders.map(reminderJson),
			})
		}
		case 'calendar': {
			await calendars.load()
			const calendar = calendars.all.find((item) => item.id === payload.resourceId)
			return makeSnapshot(
				payload,
				title,
				url,
				[`# ${calendar?.name || title}`, '', `link: ${url}`].join('\n'),
				{ calendar: calendar ? { ...calendar } : null }
			)
		}
		case 'agent':
			return makeSnapshot(
				payload,
				title,
				url,
				[`# ${title}`, '', `link: ${url}`].join('\n'),
				{}
			)
	}
}
