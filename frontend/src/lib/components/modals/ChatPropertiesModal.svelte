<script lang="ts">
	import { api } from '$lib/api/client'
	import type { components } from '$lib/api/types'
	import type { Component } from 'svelte'
	import {
		archiveThreadFromProperties,
		confirmDeleteThread,
		leaveThread,
		markThreadReadFromProperties,
		muteThreadFromProperties,
		removeThreadParticipant,
		saveThreadProperties,
		setThreadAgentMentionReply,
		shareThread,
		type ThreadParticipant,
	} from '$lib/chat/threadProperties'
	import AgentAvatar from '$lib/components/chat/AgentAvatar.svelte'
	import TagEditor from '$lib/components/common/TagEditor.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import BellSlash from '$lib/components/icons/BellSlash.svelte'
	import Brain from '$lib/components/icons/Brain.svelte'
	import ChatCheck from '$lib/components/icons/ChatCheck.svelte'
	import Note from '$lib/components/icons/Note.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import Tag from '$lib/components/icons/Tag.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import UserPlus from '$lib/components/icons/UserPlus.svelte'
	import ConversationAvatar from '$lib/components/messages/ConversationAvatar.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { ModalFormDirty } from '$lib/components/modals/formDirty.svelte'
	import ModalActions from '$lib/components/modals/ModalActions.svelte'
	import ModalSaveButton from '$lib/components/modals/ModalSaveButton.svelte'
	import ThreadAddParticipantsModal, {
		type ParticipantPickerKind,
	} from '$lib/components/modals/ThreadAddParticipantsModal.svelte'
	import { ActionTile, DropdownSelect, Skeleton, Switch } from '$lib/components/primitives'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
	import { agents } from '$lib/stores/agents.svelte'
	import { chat, isPeopleThread, type Thread } from '$lib/stores/chat.svelte'
	import { messages } from '$lib/stores/messages.svelte'
	import { showError } from '$lib/stores/notifications.svelte'
	import {
		canAdminAccessLevel,
		canDeleteAccessLevel,
		canEditAccessLevel,
		resourceAccess,
	} from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import {
		conversationDisplay,
		participantFace,
		type ConversationFace,
	} from '$lib/utils/conversationDisplay'
	import { byAuthor, metadataLine } from '$lib/utils/resourceAuthors'

	type ThreadSummaryRecord = components['schemas']['ThreadSummaryRecord']

	interface RosterRow {
		id: string
		label: string
		face: ConversationFace
		badges: string[]
		participant: ThreadParticipant
		isSelf: boolean
		canRemove: boolean
	}

	interface Props {
		open: boolean
		thread: Thread | null
		onClose: () => void
	}

	let { open, thread, onClose }: Props = $props()

	let title = $state('')
	let tags = $state<string[]>([])
	let error = $state<string | null>(null)
	let isSaving = $state(false)

	const tagPreview = $derived(tags.join(', ') || 'no tags')
	const threadAccessLevel = $derived(
		thread ? resourceAccess.level('thread', thread.id, thread.owner_id) : null
	)
	const canEditThread = $derived(canEditAccessLevel(threadAccessLevel))
	const canAdminThread = $derived(canAdminAccessLevel(threadAccessLevel))
	const canDeleteThread = $derived(canDeleteAccessLevel(threadAccessLevel))
	const authorLabel = $derived(session.authorLabel(thread?.owner_id))
	const previewSubtitle = $derived(metadataLine(byAuthor(authorLabel), tagPreview))
	const chatVisual = resourceVisual('thread')
	const ChatIcon = chatVisual.icon
	const chatAccentStyle = resourceAccentStyle('thread')
	const missingTitle = $derived(!thread?.title?.trim())
	const missingTags = $derived(!thread?.tags || thread.tags.length === 0)
	let latestCatalogSummary = $state<ThreadSummaryRecord | null>(null)
	let isLoadingSummary = $state(false)
	let isGeneratingMetadata = $state(false)
	let summaryLoadKey = ''
	const missingSummary = $derived(!latestCatalogSummary?.content.trim())
	const canGenerateMetadata = $derived(
		canEditThread && (missingTitle || missingTags || (!isLoadingSummary && missingSummary))
	)

	const isMuted = $derived(thread ? messages.isMuted(thread.id) : false)
	/** the switch moves first; a failed write puts it back. */
	let muteDraft = $derived(isMuted)
	let isTogglingMute = $state(false)
	const unreadCount = $derived(thread ? messages.unreadCount(thread.id) : 0)
	let isMarkingRead = $state(false)

	// the faces and roster come off the thread that is already loaded here.
	const people = $derived(thread ? conversationDisplay(thread, session.currentUserId) : null)
	const isPeople = $derived(thread ? isPeopleThread(thread) : false)
	const roster = $derived.by((): RosterRow[] => {
		if (!thread || !isPeople) return []
		return (thread.participants ?? []).map((participant): RosterRow => {
			const face = participantFace(participant)
			const isSelf =
				participant.kind === 'user' && participant.user.id === session.currentUserId
			// every label beside a name is a badge, so they all read the same way.
			const badges: string[] = []
			if (participant.is_owner) badges.push('owner')
			else if (participant.kind === 'agent') badges.push('agent')
			else if (participant.kind === 'group') badges.push('group')
			if (isSelf) badges.push('you')
			return {
				id: participant.id,
				label: face.label,
				face,
				badges,
				participant,
				isSelf,
				// leaving is yours to do; taking anyone else out of the chat is an
				// admin call, and the agents follow the edit gate they always have.
				canRemove: participant.kind === 'agent' ? canEditThread : isSelf || canAdminThread,
			}
		})
	})
	// the agents lead the roster; everyone else keeps the thread's own order.
	const agentRows = $derived(roster.filter((row) => row.participant.kind === 'agent'))
	const memberRows = $derived(roster.filter((row) => row.participant.kind !== 'agent'))
	const addableAgents = $derived(
		agents.list.filter((agent) => !agentRows.some((row) => row.face.id === agent.id))
	)
	const mentionReplyOptions = [
		{ value: 'inherit', label: 'use agent default' },
		{ value: 'on', label: 'reply when mentioned' },
		{ value: 'off', label: 'never reply automatically' },
	]

	/** one roster write at a time, so every row action can share the flag. */
	let busyRowId = $state<string | null>(null)
	const rosterBusy = $derived(isSaving || busyRowId !== null)

	// which picker the roster has open, if any. both open the same modal.
	let pickerKind = $state<ParticipantPickerKind | null>(null)
	const pickerExcludeIds = $derived(
		(pickerKind === 'agents' ? agentRows : memberRows).map((row) => row.face.id)
	)

	const form = new ModalFormDirty(() => ({ title, tags }))

	// seed the form once per opened thread: a live list update behind the modal
	// must not overwrite what is being typed into it.
	let seededThreadId: string | null = null
	$effect(() => {
		if (!open || !thread) {
			seededThreadId = null
			return
		}
		if (seededThreadId === thread.id) return
		seededThreadId = thread.id
		title = thread.title ?? ''
		tags = Array.isArray(thread.tags) ? [...thread.tags] : []
		error = null
		form.reset()
	})

	$effect(() => {
		const accessKey = open && thread ? `${thread.id}:${resourceAccess.version}` : ''
		if (open && thread?.owner_id && thread.owner_id !== session.currentUserId) {
			void session.ensureUsers([thread.owner_id])
		}
		if (open && thread && accessKey)
			void resourceAccess.ensure('thread', thread.id, thread.owner_id)
	})

	$effect(() => {
		if (!open || !thread) {
			latestCatalogSummary = null
			return
		}
		void loadCatalogSummary(thread.id)
	})

	// mute and unread live on the participant, not on the thread payload: seed
	// both so the modal tells the truth when it opens away from the inbox.
	$effect(() => {
		if (!open || !thread) return
		void chat.fetchUnreadCounts()
		if (isPeople && !messages.hasLoaded) void messages.loadMuted()
		if (isPeople) void agents.load()
	})

	// the picker is scratch state: it never survives a close.
	$effect(() => {
		if (!open) pickerKind = null
	})

	function displayTitle(value: string): string {
		const trimmed = value.trim()
		return trimmed || thread?.title || 'new chat'
	}

	function newestSummary(records: ThreadSummaryRecord[]): ThreadSummaryRecord | null {
		return (
			[...records].sort((a, b) => {
				const aTime = Date.parse(a.updated_at || a.created_at)
				const bTime = Date.parse(b.updated_at || b.created_at)
				return bTime - aTime
			})[0] ?? null
		)
	}

	async function loadCatalogSummary(threadId: string): Promise<void> {
		const loadKey = `${threadId}:${Date.now()}`
		summaryLoadKey = loadKey
		isLoadingSummary = true
		try {
			const { data, error } = await api.GET('/v1/threads/{thread_id}/summaries', {
				params: {
					path: { thread_id: threadId },
					query: { purpose: 'catalog', include_superseded: false },
				},
			})
			if (summaryLoadKey !== loadKey) return
			latestCatalogSummary = error || !data ? null : newestSummary(data)
		} finally {
			if (summaryLoadKey === loadKey) isLoadingSummary = false
		}
	}

	function applyGeneratedThread(generated: Thread): void {
		chat.threadCache.set(generated)
		chat.updateRecentThread(generated.id, () => generated, false)
		if (chat.activeThread?.id === generated.id) chat.activeThread = generated
		title = generated.title ?? ''
		tags = generated.tags ?? []
	}

	async function generateMetadata(): Promise<void> {
		if (!thread || isGeneratingMetadata) return
		isGeneratingMetadata = true
		try {
			const { data, error } = await api.POST('/v1/threads/{thread_id}/maintenance/run', {
				params: { path: { thread_id: thread.id } },
				body: { replace_metadata: false },
			})
			if (error || !data) {
				showError('could not generate chat metadata')
				return
			}
			applyGeneratedThread(data)
			await loadCatalogSummary(data.id)
		} catch {
			showError('could not generate chat metadata')
		} finally {
			isGeneratingMetadata = false
		}
	}

	function handleSubmit(event: SubmitEvent): void {
		event.preventDefault()
		if (!canEditThread || isSaving || !form.dirty) return
		void save()
	}

	async function save(): Promise<void> {
		const target = thread
		if (!target || isSaving) return
		isSaving = true
		error = null
		if (await saveThreadProperties(target, title, tags)) onClose()
		else error = 'could not save changes'
		isSaving = false
	}

	/** every action that leaves this modal behind closes it first. */
	function runAndClose(action: (target: Thread) => void): void {
		const target = thread
		if (!target || isSaving) return
		onClose()
		action(target)
	}

	async function toggleMute(next: boolean): Promise<void> {
		const target = thread
		if (!target || isTogglingMute) return
		isTogglingMute = true
		const applied = await muteThreadFromProperties(target, next)
		if (applied === null) muteDraft = isMuted
		isTogglingMute = false
	}

	async function markRead(): Promise<void> {
		const target = thread
		if (!target || isMarkingRead || unreadCount === 0) return
		isMarkingRead = true
		try {
			await markThreadReadFromProperties(target)
		} finally {
			isMarkingRead = false
		}
	}

	function mentionReplyValue(participant: ThreadParticipant): string {
		if (participant.kind !== 'agent') return 'inherit'
		if (participant.invoke_on_mention === true) return 'on'
		if (participant.invoke_on_mention === false) return 'off'
		return 'inherit'
	}

	async function removeRow(row: RosterRow): Promise<void> {
		const target = thread
		if (!target || rosterBusy) return
		busyRowId = row.id
		error = null
		try {
			if (row.isSelf) {
				if (await leaveThread(target, row.participant)) onClose()
				else error = 'could not leave this chat'
				return
			}
			if (!(await removeThreadParticipant(target, row.participant)))
				error = `could not remove ${row.face.label}`
		} finally {
			busyRowId = null
		}
	}

	async function changeMentionReply(row: RosterRow, choice: string): Promise<void> {
		const target = thread
		if (!target || rosterBusy || row.participant.kind !== 'agent') return
		busyRowId = row.id
		error = null
		try {
			const invokeOnMention = choice === 'inherit' ? null : choice === 'on'
			if (!(await setThreadAgentMentionReply(target, row.face.id, invokeOnMention)))
				error = 'could not update the reply mode'
		} finally {
			busyRowId = null
		}
	}

	const panelClass =
		'border-foreground/13 bg-background/70 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] backdrop-blur-[16px] backdrop-saturate-[1.08]'
	const sectionClass = `${panelClass} grid min-w-0 gap-2 rounded-[18px] border p-3`
	const sectionTitleClass =
		'text-foreground/45 px-1 text-[0.68rem] font-semibold tracking-[0.14em] uppercase'
	const nameInputClass =
		'text-foreground w-full max-w-[22rem] min-w-0 rounded-2xl border border-transparent bg-transparent px-3 py-1 text-center text-xl font-semibold outline-none transition-colors duration-150 placeholder:text-foreground/30 hover:border-foreground/10 hover:bg-foreground/4 focus:border-[color-mix(in_oklch,var(--accent-primary)_45%,transparent)] focus:bg-foreground/6'
	const destructiveTitleClass =
		'px-1 text-[0.68rem] font-semibold tracking-[0.14em] text-red-500/75 uppercase dark:text-red-400/75'
	const rosterRowClass = 'flex min-w-0 items-center gap-3 rounded-xl px-1 py-1.5'
	/** the app's destructive action at row scale, as the message-request rows draw it. */
	const rowActionClass =
		'rounded-pill text-red-500/70 hover:bg-red-500/10 shrink-0 cursor-pointer px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-55'
	/** the app's neutral identity badge, as the temporary-chat pill above draws it. */
	const rowBadgeClass =
		'rounded-pill border-foreground/12 bg-foreground/6 text-foreground/60 shrink-0 border px-2.5 py-0.5 text-[0.68rem] font-medium'
	/** a 32px round slot: every row in these sections leads with one. */
	const rowIconSlotClass =
		'bg-foreground/10 flex size-8 shrink-0 items-center justify-center rounded-full'
	const addRowClass =
		'hover:bg-foreground/5 flex min-w-0 cursor-pointer items-center gap-3 rounded-xl px-1 py-1.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-55'
	const addRowIconClass =
		'flex size-8 shrink-0 items-center justify-center rounded-full bg-(--accent-primary)/15 text-(--accent-primary)'
	/** the app's destructive pill, as the confirm dialog draws it. */
	const destructivePillClass =
		'rounded-pill inline-flex cursor-pointer items-center justify-self-start border border-red-500/25 bg-red-500/20 px-4 py-2 text-sm text-red-100 transition-colors duration-150 hover:bg-red-500/30 disabled:cursor-not-allowed disabled:opacity-60'
</script>

{#snippet addRow(label: string, icon: Component<{ class?: string }>, onclick: () => void)}
	{@const Icon = icon}
	<button type="button" class={addRowClass} disabled={rosterBusy} {onclick}>
		<span class={addRowIconClass}>
			<Icon class="size-4" />
		</span>
		<span class="text-sm font-medium text-(--accent-primary)">{label}</span>
	</button>
{/snippet}

{#snippet rosterRow(row: RosterRow)}
	{@const isAgent = row.participant.kind === 'agent'}
	<li class="grid min-w-0 gap-1">
		<div class={isAgent ? `${rosterRowClass} bg-(--accent-primary)/6` : rosterRowClass}>
			{#if isAgent}
				<AgentAvatar
					name={row.face.label}
					avatarUrl={row.face.avatarUrl}
					class="size-8"
					textClass="text-[0.68rem]"
				/>
			{:else}
				<ConversationAvatar
					faces={[row.face]}
					isGroup={false}
					sizeClass="size-8"
					textClass="text-[0.68rem]"
				/>
			{/if}
			<span class="text-foreground/85 min-w-0 flex-1 truncate text-sm">{row.label}</span>
			{#each row.badges as badge (badge)}
				<span class={rowBadgeClass}>{badge}</span>
			{/each}
			{#if row.canRemove}
				<button
					type="button"
					class={rowActionClass}
					disabled={rosterBusy}
					onclick={() => void removeRow(row)}
				>
					{#if busyRowId === row.id}
						<ShimmerText className="inline-block">
							{row.isSelf ? 'leaving' : 'removing'}
						</ShimmerText>
					{:else}
						{row.isSelf ? 'leave' : 'remove'}
					{/if}
				</button>
			{/if}
		</div>
		{#if isAgent && canEditThread}
			<div class="px-1 pb-0.5">
				<DropdownSelect
					options={mentionReplyOptions}
					value={mentionReplyValue(row.participant)}
					onchange={(value) => void changeMentionReply(row, value)}
					disabled={rosterBusy}
					ariaLabel={`when ${row.face.label} is mentioned`}
				/>
			</div>
		{/if}
	</li>
{/snippet}

<BaseModal
	{open}
	title="chat info"
	onClose={() => !isSaving && onClose()}
	widthClassName="max-w-lg"
>
	{#if thread}
		<form class="grid gap-3" style={chatAccentStyle} onsubmit={handleSubmit}>
			<header class="grid justify-items-center gap-3 pt-1 pb-1 text-center" data-identity>
				{#if isPeople && people}
					<span
						class="ring-foreground/12 rounded-full shadow-[0_10px_28px_rgb(0_0_0/0.22)] ring-1 ring-inset"
					>
						<ConversationAvatar
							faces={people.faces}
							isGroup={people.isGroup}
							sizeClass="size-24"
							textClass="text-2xl"
						/>
					</span>
				{:else}
					<span
						class="flex size-24 items-center justify-center rounded-full border border-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_12%,transparent)] text-(--accent-primary) shadow-[0_10px_28px_rgb(0_0_0/0.18)]"
					>
						<ChatIcon variant="solid" class="size-10" />
					</span>
				{/if}

				<div class="grid w-full min-w-0 justify-items-center gap-1">
					{#if canEditThread}
						<label class="sr-only" for="chat-title">chat name</label>
						<input
							id="chat-title"
							class={nameInputClass}
							bind:value={title}
							placeholder="new chat"
							disabled={isSaving}
						/>
					{:else}
						<h3 class="text-foreground min-w-0 truncate text-xl font-semibold">
							{displayTitle(title)}
						</h3>
					{/if}
					<p class="text-foreground/55 min-w-0 max-w-full truncate text-xs">
						{previewSubtitle}
					</p>
					{#if thread.is_temporary}
						<span
							class="rounded-pill border-foreground/12 bg-foreground/6 text-foreground/60 mt-0.5 border px-2.5 py-0.5 text-[0.68rem] font-medium"
						>
							temporary chat
						</span>
					{/if}
				</div>
			</header>

			<div class="flex flex-wrap items-start justify-center gap-2 pb-1">
				<ActionTile
					label="share"
					icon={Share}
					onclick={() => runAndClose(shareThread)}
					disabled={isSaving}
				/>
				<ActionTile
					label="archive"
					icon={ArchiveBox}
					onclick={() =>
						runAndClose((target) => void archiveThreadFromProperties(target))}
					disabled={isSaving}
				/>
				<ActionTile
					label="mark as read"
					icon={ChatCheck}
					onclick={() => void markRead()}
					disabled={isSaving || isMarkingRead || unreadCount === 0}
					workingLabel={isMarkingRead ? 'marking read' : null}
				/>
				{#if canGenerateMetadata}
					<ActionTile
						label="generate info"
						icon={Sparkles}
						onclick={() => void generateMetadata()}
						disabled={isSaving || isGeneratingMetadata}
						workingLabel={isGeneratingMetadata ? 'generating' : null}
					/>
				{/if}
			</div>

			{#if isPeople}
				<section class={sectionClass} data-section="notifications">
					<h4 class={sectionTitleClass}>notifications</h4>
					<div class="flex min-w-0 items-center gap-3 px-1 py-0.5">
						<span class={rowIconSlotClass}>
							<BellSlash class="text-foreground/60 size-4" />
						</span>
						<span
							id="chat-mute-label"
							class="text-foreground/85 min-w-0 flex-1 text-sm"
						>
							mute
						</span>
						<Switch
							size="md"
							bind:checked={muteDraft}
							onchange={(next) => void toggleMute(next)}
							disabled={isSaving || isTogglingMute}
							ariaLabelledbyId="chat-mute-label"
						/>
					</div>
				</section>
			{/if}

			{#if roster.length > 0}
				<section class={sectionClass} data-section="participants">
					<h4 class={sectionTitleClass}>
						{roster.length === 1 ? '1 participant' : `${roster.length} participants`}
					</h4>
					<ul class="grid gap-0.5">
						{#each agentRows as row (row.id)}
							{@render rosterRow(row)}
						{/each}
						{#if canEditThread && addableAgents.length > 0}
							<li class="min-w-0">
								{@render addRow('add agents', Brain, () => (pickerKind = 'agents'))}
							</li>
						{/if}
						{#each memberRows as row (row.id)}
							{@render rosterRow(row)}
						{/each}
						{#if canEditThread}
							<li class="min-w-0">
								{@render addRow(
									'add members',
									UserPlus,
									() => (pickerKind = 'members')
								)}
							</li>
						{/if}
					</ul>
				</section>
			{/if}

			<section class={sectionClass} data-section="tags">
				<label class={sectionTitleClass} for="chat-tags">tags</label>
				{#if canEditThread || tags.length > 0}
					<TagEditor
						icon={Tag}
						inputId="chat-tags"
						bind:value={tags}
						disabled={isSaving || !canEditThread}
					/>
				{:else}
					<EmptyState label="no tags yet" compact>
						{#snippet icon()}
							<Tag class="size-5" />
						{/snippet}
					</EmptyState>
				{/if}
			</section>

			<section class={sectionClass} data-section="summary">
				<h4 class={sectionTitleClass} id="chat-summary-label">summary</h4>
				<div
					class="text-foreground/72 min-h-10 px-1 text-sm leading-6 wrap-break-word whitespace-pre-wrap select-text"
					aria-labelledby="chat-summary-label"
				>
					{#if isLoadingSummary}
						<Skeleton shape="lines" lines={2} />
					{:else if latestCatalogSummary?.content.trim()}
						{latestCatalogSummary.content.trim()}
					{:else}
						<EmptyState
							label="no summary yet"
							description={canGenerateMetadata
								? 'generate info writes one from this chat'
								: undefined}
							compact
						>
							{#snippet icon()}
								<Note class="size-5" />
							{/snippet}
						</EmptyState>
					{/if}
				</div>
			</section>

			{#if error}
				<div
					class="rounded-container border-foreground/10 bg-foreground/5 text-foreground/70 border px-3 py-2 text-sm"
				>
					{error}
				</div>
			{/if}

			{#if canDeleteThread}
				<section
					class="{sectionClass} border-red-500/22 bg-red-500/6"
					data-section="destructive"
				>
					<h4 class={destructiveTitleClass}>danger zone</h4>
					<button
						type="button"
						class={destructivePillClass}
						disabled={isSaving}
						onclick={() => runAndClose(confirmDeleteThread)}
					>
						<Trash class="h-4 w-4" />
						<span class="ml-2">delete chat</span>
					</button>
				</section>
			{/if}

			{#if canEditThread}
				<ModalActions class="pt-1">
					<ModalSaveButton dirty={form.dirty} saving={isSaving} />
				</ModalActions>
			{/if}
		</form>
	{:else}
		<div class="text-foreground/65 text-sm">chat not found</div>
	{/if}
</BaseModal>

<ThreadAddParticipantsModal
	open={pickerKind !== null}
	{thread}
	kind={pickerKind ?? 'members'}
	excludeIds={pickerExcludeIds}
	onClose={() => (pickerKind = null)}
/>
