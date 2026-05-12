<script lang="ts">
	import { browser } from '$app/environment'
	import { base } from '$app/paths'
	import { api } from '$lib/api/client'
	import type { components } from '$lib/api/types'
	import { contentPartsToText } from '$lib/chat/helpers'
	import ShieldCheck from '$lib/components/icons/ShieldCheck.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { calendars } from '$lib/stores/calendars.svelte'
	import { chat } from '$lib/stores/chat.svelte'
	import { downloadFile, files } from '$lib/stores/files.svelte'
	import { friends } from '$lib/stores/friends.svelte'
	import { groups } from '$lib/stores/groups.svelte'
	import type { ResourceAccessPayload } from '$lib/stores/modals.svelte'
	import { notes } from '$lib/stores/notes.svelte'
	import { notifications, showError } from '$lib/stores/notifications.svelte'
	import { projects } from '$lib/stores/projects.svelte'
	import { reminders } from '$lib/stores/reminders.svelte'
	import {
		canShareAccessLevel,
		resourceAccess,
		type AccessLevel,
		type AccessRuleCreate,
		type AccessRuleResponse,
	} from '$lib/stores/resourceAccess.svelte'
	import { faviconCandidates } from '$lib/utils/favicons'
	import { userDisplayName } from '$lib/utils/resourceAuthors'
	import ResourceAccessActions from './ResourceAccessActions.svelte'
	import ResourceAccessHeader from './ResourceAccessHeader.svelte'
	import ResourceAccessPeople from './ResourceAccessPeople.svelte'
	import {
		queryString,
		resourceLabel,
		resourcePath,
		shareIconFailureKey,
		type ExportFormat,
		type RuleEntry,
		type ShareTarget,
		type ShareTargetId,
		type UserPick,
		type UserResult,
	} from './resourceAccessModal'

	type ApiFile = components['schemas']['File']
	type ApiMessage = components['schemas']['Message']
	type ApiThread = components['schemas']['Thread']

	interface Props {
		open: boolean
		payload: ResourceAccessPayload | null
		onClose: () => void
	}

	let { open, payload, onClose }: Props = $props()

	let rules = $state<RuleEntry[]>([])
	let isSaving = $state(false)
	let isLoading = $state(false)
	let saveError = $state<string | null>(null)
	let workingAction = $state<string | null>(null)

	let searchQuery = $state('')
	let searchResults = $state<UserResult[]>([])
	let failedShareIcons = $state<string[]>([])
	let searchDebounce: ReturnType<typeof setTimeout> | null = null
	let rulesLoadKey = ''
	let rulesLoadVersion = -1

	let dragIndex = $state<number | null>(null)
	let dragOverIndex = $state<number | null>(null)

	const currentLevel = $derived(
		payload ? resourceAccess.level(payload.resourceType, payload.resourceId) : null
	)
	const canManageSharing = $derived(canShareAccessLevel(currentLevel))
	const shareTitle = $derived(payload?.title?.trim() || resourceLabel(payload?.resourceType))
	const sharePath = $derived(
		payload ? resourcePath(payload.resourceType, payload.resourceId) : '/'
	)
	const sharePathWithBase = $derived(`${base}${sharePath}`)
	const shareUrl = $derived(
		browser ? new URL(sharePathWithBase, window.location.origin).toString() : sharePathWithBase
	)
	const mailHref = $derived(`mailto:?${queryString({ subject: shareTitle, body: shareUrl })}`)
	const whatsappHref = $derived(
		`https://wa.me/?${queryString({ text: `${shareTitle} ${shareUrl}` })}`
	)
	const telegramHref = $derived(
		`https://t.me/share/url?${queryString({ url: shareUrl, text: shareTitle })}`
	)
	const xHref = $derived(
		`https://x.com/intent/tweet?${queryString({ url: shareUrl, text: shareTitle })}`
	)
	const shareTargets = $derived<ShareTarget[]>([
		{
			id: 'whatsapp',
			label: 'whatsapp',
			href: whatsappHref,
			origin: 'https://www.whatsapp.com',
		},
		{
			id: 'telegram',
			label: 'telegram',
			href: telegramHref,
			origin: 'https://telegram.org',
		},
		{
			id: 'x',
			label: 'x',
			href: xHref,
			origin: 'https://x.com',
		},
	])
	const canNativeShare = $derived(
		browser && typeof navigator !== 'undefined' && typeof navigator.share === 'function'
	)

	const filteredGroups = $derived(
		groups.list.filter(
			(group) => !searchQuery || group.name.toLowerCase().includes(searchQuery.toLowerCase())
		)
	)
	const filteredFriends = $derived.by(() => {
		const query = searchQuery.trim().toLowerCase()
		return friends.list.filter((friend) => {
			if (rules.some((rule) => rule.subjectUserId === friend.id)) return false
			if (!query) return true
			return userLabel(friend).toLowerCase().includes(query)
		})
	})

	const panelClass =
		'liquid-glass liquid-glass--frosted rounded-container border-foreground/10 bg-foreground/4 border'
	const actionButtonClass =
		'rounded-pill inline-flex min-h-9 cursor-pointer items-center justify-center gap-1.5 px-4 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
	const quietButtonClass = `${actionButtonClass} border-foreground/12 text-foreground/80 hover:bg-foreground/6 border bg-transparent`
	const primaryButtonClass = `${actionButtonClass} bg-(--accent-primary) text-white hover:brightness-[1.06]`
	const iconBoxClass =
		'flex h-11 w-11 shrink-0 items-center justify-center rounded-[15px] border border-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_12%,transparent)] text-(--accent-primary)'
	const inputClass =
		'rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full border py-2.5 pr-4 pl-10 text-sm transition-colors outline-none'
	const THREAD_EXPORT_MESSAGE_LIMIT = 500
	const MAX_CLIPBOARD_SNAPSHOT_CHARS = 120_000

	function shareIconUrls(target: ShareTarget): string[] {
		return faviconCandidates(target.origin)
	}

	function activeShareIconUrl(target: ShareTarget): string | undefined {
		return shareIconUrls(target).find(
			(url) => !failedShareIcons.includes(shareIconFailureKey(target.id, url))
		)
	}

	function markShareIconFailed(targetId: ShareTargetId, url: string): void {
		const key = shareIconFailureKey(targetId, url)
		if (failedShareIcons.includes(key)) return
		failedShareIcons = [...failedShareIcons, key]
	}

	function ruleLocalId(rule: AccessRuleResponse, index: number): string {
		return (
			rule.id ??
			rule.subject_user_id ??
			rule.subject_group_id ??
			rule.subject_role_id ??
			`rule-${index}`
		)
	}

	function ruleSubjectLabel(rule: AccessRuleResponse): string {
		if (rule.subject_user_id) return rule.subject_user_id
		if (rule.subject_group_id) return rule.subject_group_id
		if (rule.subject_role_id) return rule.subject_role_id
		return 'someone'
	}

	function toRuleEntry(rule: AccessRuleResponse, index: number): RuleEntry {
		return {
			localId: ruleLocalId(rule, index),
			id: rule.id,
			subjectLabel: ruleSubjectLabel(rule),
			subjectUserId: rule.subject_user_id ?? null,
			subjectGroupId: rule.subject_group_id ?? null,
			subjectRoleId: rule.subject_role_id ?? null,
			level: rule.level,
			orderIndex: index,
		}
	}

	function makeNewRuleId(subjectType: 'user' | 'group' | 'role', subjectId: string): string {
		return `new-${subjectType}-${subjectId}`
	}

	function userLabel(user: UserPick): string {
		return userDisplayName(user) ?? user.id
	}

	async function loadRules(): Promise<void> {
		if (!payload || !canManageSharing) return
		const key = `${payload.resourceType}:${payload.resourceId}`
		const version = resourceAccess.version
		if (rulesLoadKey === key && rulesLoadVersion === version) return
		isLoading = true
		try {
			const fetched = await resourceAccess.ensureRules(
				payload.resourceType,
				payload.resourceId
			)
			rules = fetched.map(toRuleEntry)
			rulesLoadKey = key
			rulesLoadVersion = version
		} finally {
			isLoading = false
		}
	}

	function showSaveError(): void {
		const message = 'could not save sharing'
		saveError = message
		showError(message)
	}

	async function saveRules(): Promise<void> {
		if (!payload || !canManageSharing) return
		isSaving = true
		saveError = null
		const body: AccessRuleCreate[] = rules.map((rule, index) => ({
			subject_user_id: rule.subjectUserId ?? undefined,
			subject_group_id: rule.subjectGroupId ?? undefined,
			subject_role_id: rule.subjectRoleId ?? undefined,
			level: rule.level,
			order_index: index,
		}))
		try {
			const saved = await resourceAccess.replaceRules(
				payload.resourceType,
				payload.resourceId,
				body
			)
			if (!saved) {
				showSaveError()
				return
			}
			rules = saved.map(toRuleEntry)
			notifications.pushEphemeralToast('success', 'sharing saved')
			onClose()
		} catch {
			showSaveError()
		} finally {
			isSaving = false
		}
	}

	async function doSearch(query: string): Promise<void> {
		if (!canManageSharing || !query.trim()) {
			searchResults = []
			return
		}
		try {
			const { data } = await api.GET('/v1/users/search', {
				params: { query: { q: query.trim(), limit: 10 } },
			})
			searchResults = data ?? []
		} catch {
			searchResults = []
		}
	}

	function onSearchInput(event: Event): void {
		const target = event.currentTarget
		if (!(target instanceof HTMLInputElement)) return
		searchQuery = target.value
		if (searchDebounce) clearTimeout(searchDebounce)
		searchDebounce = setTimeout(() => void doSearch(searchQuery), 300)
	}

	function addUserRule(user: UserPick, level: AccessLevel = 'reader'): void {
		if (rules.some((rule) => rule.subjectUserId === user.id)) return
		rules = [
			...rules,
			{
				localId: makeNewRuleId('user', user.id),
				id: null,
				subjectLabel: userLabel(user),
				subjectUserId: user.id,
				subjectGroupId: null,
				subjectRoleId: null,
				level,
				orderIndex: rules.length,
			},
		]
		searchQuery = ''
		searchResults = []
	}

	function addGroupRule(groupId: string, label: string, level: AccessLevel = 'reader'): void {
		if (rules.some((rule) => rule.subjectGroupId === groupId)) return
		rules = [
			...rules,
			{
				localId: makeNewRuleId('group', groupId),
				id: null,
				subjectLabel: label,
				subjectUserId: null,
				subjectGroupId: groupId,
				subjectRoleId: null,
				level,
				orderIndex: rules.length,
			},
		]
	}

	function removeRule(index: number): void {
		rules = rules.filter((_, ruleIndex) => ruleIndex !== index)
	}

	function setLevel(index: number, level: AccessLevel): void {
		rules = rules.map((rule, ruleIndex) => (ruleIndex === index ? { ...rule, level } : rule))
	}

	function onDragStart(event: DragEvent, index: number): void {
		dragIndex = index
		if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
	}

	function onDragOver(event: DragEvent, index: number): void {
		event.preventDefault()
		dragOverIndex = index
		if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
	}

	function onDrop(event: DragEvent, toIndex: number): void {
		event.preventDefault()
		if (dragIndex === null || dragIndex === toIndex) {
			dragIndex = null
			dragOverIndex = null
			return
		}
		const reordered = [...rules]
		const [moved] = reordered.splice(dragIndex, 1)
		reordered.splice(toIndex, 0, moved)
		rules = reordered
		dragIndex = null
		dragOverIndex = null
	}

	function onDragEnd(): void {
		dragIndex = null
		dragOverIndex = null
	}

	function cleanFilename(value: string): string {
		return (
			value
				.toLowerCase()
				.replace(/[^a-z0-9]+/g, '-')
				.replace(/(^-|-$)/g, '') || 'share'
		)
	}

	function downloadTextFile(filename: string, content: string, mimeType: string): void {
		const blob = new Blob([content], { type: mimeType })
		const href = URL.createObjectURL(blob)
		const anchor = document.createElement('a')
		anchor.href = href
		anchor.download = filename
		document.body.appendChild(anchor)
		anchor.click()
		document.body.removeChild(anchor)
		URL.revokeObjectURL(href)
	}

	async function copyText(value: string, successMessage: string): Promise<void> {
		if (value.length > MAX_CLIPBOARD_SNAPSHOT_CHARS) {
			showError('too large to copy; download instead')
			return
		}
		try {
			await navigator.clipboard.writeText(value)
			notifications.pushEphemeralToast('success', successMessage)
		} catch {
			showError('could not copy')
		}
	}

	async function withWorking(actionId: string, callback: () => Promise<void>): Promise<void> {
		workingAction = actionId
		try {
			await callback()
		} finally {
			workingAction = null
		}
	}

	function threadTitle(thread: ApiThread | null): string {
		return thread?.title?.trim() || shareTitle
	}

	function messageText(message: ApiMessage): string {
		return contentPartsToText(message.content).trim()
	}

	function plainTextFromMarkdown(markdown: string): string {
		return markdown
			.replace(/^#{1,6}\s+/gm, '')
			.replace(/^[-*]\s+/gm, '- ')
			.trim()
	}

	function exportExtension(format: ExportFormat): string {
		return format === 'json' ? 'json' : format
	}

	function exportMimeType(format: ExportFormat): string {
		if (format === 'json') return 'application/json;charset=utf-8'
		if (format === 'txt') return 'text/plain;charset=utf-8'
		return 'text/markdown;charset=utf-8'
	}

	function exportSnapshot(markdown: string, format: ExportFormat): string {
		if (format === 'md') return markdown
		if (format === 'txt') return plainTextFromMarkdown(markdown)
		return JSON.stringify(
			{
				resource_type: payload?.resourceType ?? null,
				resource_id: payload?.resourceId ?? null,
				title: shareTitle,
				url: shareUrl,
				markdown,
			},
			null,
			2
		)
	}

	async function buildResourceSnapshot(): Promise<string> {
		if (!payload) return shareUrl
		const title = shareTitle
		switch (payload.resourceType) {
			case 'thread': {
				const thread = await chat.threadCache.getThread(payload.resourceId)
				const { messages } = await chat.threadCache.getMessages(
					payload.resourceId,
					0,
					THREAD_EXPORT_MESSAGE_LIMIT
				)
				const lines = [`# ${threadTitle(thread)}`, '', `link: ${shareUrl}`, '']
				for (const message of messages) {
					const text = messageText(message)
					if (!text) continue
					lines.push(`## ${message.type}`, '', text, '')
				}
				return lines.join('\n')
			}
			case 'note': {
				await notes.load()
				const note = notes.get(payload.resourceId)
				return [
					`# ${note?.title || title}`,
					'',
					note?.content ?? '',
					'',
					`link: ${shareUrl}`,
				]
					.filter(Boolean)
					.join('\n')
			}
			case 'file': {
				await files.load()
				const file = files.get(payload.resourceId) as ApiFile | null
				return [
					`# ${file?.filename || title}`,
					'',
					file?.mime_type ? `type: ${file.mime_type}` : '',
					file?.size_bytes ? `size: ${file.size_bytes} bytes` : '',
					`link: ${shareUrl}`,
				]
					.filter(Boolean)
					.join('\n')
			}
			case 'project': {
				await projects.load()
				const project = projects.getById(payload.resourceId)
				return [
					`# ${project?.name || title}`,
					'',
					project?.description ?? '',
					'',
					`link: ${shareUrl}`,
				]
					.filter(Boolean)
					.join('\n')
			}
			case 'group': {
				await groups.load()
				const group = groups.getById(payload.resourceId)
				return [
					`# ${group?.name || title}`,
					'',
					group?.description ?? '',
					'',
					`link: ${shareUrl}`,
				]
					.filter(Boolean)
					.join('\n')
			}
			case 'reminder_list': {
				await reminders.loadLists()
				const list = reminders.getListById(payload.resourceId)
				return [
					`# ${list?.name || title}`,
					'',
					list ? `total: ${list.total_count}` : '',
					list ? `pending: ${list.pending_count}` : '',
					list ? `completed: ${list.completed_count}` : '',
					`link: ${shareUrl}`,
				]
					.filter(Boolean)
					.join('\n')
			}
			case 'calendar': {
				await calendars.load()
				const calendar = calendars.all.find((item) => item.id === payload.resourceId)
				return [`# ${calendar?.name || title}`, '', `link: ${shareUrl}`].join('\n')
			}
			case 'agent':
				return [`# ${title}`, '', `link: ${shareUrl}`].join('\n')
		}
	}

	async function copyLink(): Promise<void> {
		await copyText(shareUrl, 'link copied')
	}

	async function copySnapshot(): Promise<void> {
		await withWorking('copy-snapshot', async () => {
			await copyText(exportSnapshot(await buildResourceSnapshot(), 'txt'), 'copied')
		})
	}

	async function downloadSnapshot(format: ExportFormat): Promise<void> {
		await withWorking(`download-snapshot-${format}`, async () => {
			const content = exportSnapshot(await buildResourceSnapshot(), format)
			downloadTextFile(
				`${cleanFilename(shareTitle)}.${exportExtension(format)}`,
				content,
				exportMimeType(format)
			)
		})
	}

	async function printSnapshotPdf(): Promise<void> {
		if (!browser) return
		const printWindow = window.open('', '_blank')
		if (!printWindow) {
			showError('could not open print view')
			return
		}
		await withWorking('print-snapshot', async () => {
			const content = exportSnapshot(await buildResourceSnapshot(), 'txt')
			printWindow.document.write(
				'<!doctype html><html><head><title></title><style>body{font-family:system-ui,sans-serif;margin:32px;line-height:1.5}pre{white-space:pre-wrap;font:inherit}</style></head><body><pre></pre></body></html>'
			)
			printWindow.document.title = shareTitle
			printWindow.document.querySelector('pre')?.append(document.createTextNode(content))
			printWindow.document.close()
			printWindow.focus()
			printWindow.print()
		})
	}

	async function downloadOriginalFile(): Promise<void> {
		if (!payload || payload.resourceType !== 'file') return
		await withWorking('download-file', async () => {
			await files.load()
			const file = files.get(payload.resourceId)
			await downloadFile(payload.resourceId, file?.filename ?? shareTitle)
		})
	}

	async function nativeShare(): Promise<void> {
		if (!canNativeShare) {
			await copyLink()
			return
		}
		try {
			await navigator.share({ title: shareTitle, text: shareTitle, url: shareUrl })
		} catch (error) {
			if (error instanceof DOMException && error.name === 'AbortError') return
			showError('could not share')
		}
	}

	$effect(() => {
		if (!open || !payload) return
		void resourceAccess.ensure(payload.resourceType, payload.resourceId)
	})

	$effect(() => {
		if (open && payload && canManageSharing) {
			void loadRules()
			void groups.load()
			void friends.load()
		}
	})

	$effect(() => {
		if (!open) {
			rules = []
			searchQuery = ''
			searchResults = []
			saveError = null
			workingAction = null
			failedShareIcons = []
			dragIndex = null
			dragOverIndex = null
			rulesLoadKey = ''
			rulesLoadVersion = -1
		}
	})
</script>

<BaseModal {open} title="share" {onClose} widthClassName="max-w-3xl">
	<div class="grid gap-3">
		<ResourceAccessHeader
			{panelClass}
			{iconBoxClass}
			resourceType={payload?.resourceType}
			title={shareTitle}
			url={shareUrl}
			{currentLevel}
		/>

		<ResourceAccessActions
			{panelClass}
			{quietButtonClass}
			{mailHref}
			{shareTargets}
			{workingAction}
			resourceType={payload?.resourceType}
			{activeShareIconUrl}
			{markShareIconFailed}
			{copyLink}
			{nativeShare}
			{copySnapshot}
			{downloadSnapshot}
			{printSnapshotPdf}
			{downloadOriginalFile}
		/>

		{#if canManageSharing}
			<ResourceAccessPeople
				{panelClass}
				{quietButtonClass}
				{primaryButtonClass}
				{inputClass}
				{rules}
				{searchQuery}
				{searchResults}
				{filteredFriends}
				{filteredGroups}
				{isLoading}
				{isSaving}
				{saveError}
				{dragIndex}
				{dragOverIndex}
				{userLabel}
				{onSearchInput}
				{addUserRule}
				{addGroupRule}
				{removeRule}
				{setLevel}
				{onDragStart}
				{onDragOver}
				{onDrop}
				{onDragEnd}
				{saveRules}
			/>
		{:else}
			<section class="{panelClass} flex items-start gap-3 p-4">
				<div
					class="bg-foreground/10 flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
				>
					<ShieldCheck class="h-4 w-4" />
				</div>
				<div>
					<p class="text-sm font-medium">sharing is managed by someone else</p>
					<p class="text-foreground/45 mt-1 text-sm">
						you can still send the link or export what you can view.
					</p>
				</div>
			</section>
		{/if}
	</div>
</BaseModal>
