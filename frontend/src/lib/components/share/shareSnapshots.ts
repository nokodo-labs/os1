import type { components } from '$lib/api/types'
import { contentPartsToText } from '$lib/chat/helpers'
import { calendars } from '$lib/stores/calendars.svelte'
import { chat } from '$lib/stores/chat.svelte'
import { files } from '$lib/stores/files.svelte'
import { groups } from '$lib/stores/groups.svelte'
import { buildReminderListExport, buildReminderListMarkdown } from '$lib/reminders/export'
import type { ResourceAccessPayload } from '$lib/stores/modals.svelte'
import { notes } from '$lib/stores/notes.svelte'
import { projects } from '$lib/stores/projects.svelte'
import { reminders } from '$lib/stores/reminders.svelte'
import { BASE_EXPORT_OPTION_VALUES, type ExportOptionValues } from './exportOptions'
import type { ExportFormat } from './shareModal'

type ApiFile = components['schemas']['File']
type ApiMessage = components['schemas']['Message']
type ApiThread = components['schemas']['Thread']

export type ResourceSnapshot = {
	markdown: string
	json: Record<string, unknown>
}

export type ResourceSnapshotRequest = {
	payload: ResourceAccessPayload | null
	title: string
	url: string
	threadMessageLimit?: number
	/** whatever the resource type's export options resolved to */
	options?: ExportOptionValues
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
	options = BASE_EXPORT_OPTION_VALUES,
}: ResourceSnapshotRequest): Promise<ResourceSnapshot> {
	if (!payload) return makeSnapshot(payload, title, url, url, {})
	switch (payload.resourceType) {
		case 'thread': {
			const thread = await chat.threadCache.getThread(payload.resourceId)
			const messages =
				options.threadScope === 'tree'
					? await chat.threadCache.getAllMessages(payload.resourceId, threadMessageLimit)
					: await chat.threadCache.getBranchMessages(
							payload.resourceId,
							threadMessageLimit
						)
			const lines = [`# ${threadTitle(thread, title)}`, '', `link: ${url}`, '']
			for (const message of messages) {
				const text = messageText(message)
				if (!text) continue
				lines.push(`## ${message.type}`, '', text, '')
			}
			return makeSnapshot(payload, title, url, lines.join('\n'), {
				export_scope: options.threadScope,
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
			const data = buildReminderListExport(list, listReminders)
			const markdown = buildReminderListMarkdown({ title, url, data })
			return makeSnapshot(payload, title, url, markdown, {
				list: data.list,
				counts: data.counts,
				reminders: data.reminders,
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
