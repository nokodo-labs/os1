<script lang="ts">
	import { api } from '$lib/api/client'
	import type { components } from '$lib/api/types'
	import TagEditor from '$lib/components/common/TagEditor.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import Tag from '$lib/components/icons/Tag.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
	import { chat, type Thread } from '$lib/stores/chat.svelte'
	import { showError } from '$lib/stores/notifications.svelte'
	import { canEditAccessLevel, resourceAccess } from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { byAuthor, metadataLine } from '$lib/utils/resourceAuthors'

	type ThreadSummaryRecord = components['schemas']['ThreadSummaryRecord']

	interface Props {
		open: boolean
		thread: Thread | null
		title: string
		tags: string[]
		error: string | null
		isSaving: boolean
		onClose: () => void
		onShare: () => void
		onSave: () => void
	}

	let {
		open,
		thread,
		title = $bindable(),
		tags = $bindable(),
		error,
		isSaving,
		onClose,
		onShare,
		onSave,
	}: Props = $props()

	const tagPreview = $derived(tags.join(', ') || 'no tags')
	const threadAccessLevel = $derived(
		thread ? resourceAccess.level('thread', thread.id, thread.owner_id) : null
	)
	const canEditThread = $derived(canEditAccessLevel(threadAccessLevel))
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
		if (!canEditThread) return
		onSave()
	}

	const panelClass =
		'border-foreground/13 bg-background/70 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] backdrop-blur-[16px] backdrop-saturate-[1.08]'
	const fieldClass = `${panelClass} grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 rounded-[16px] border p-3`
	const inputClass =
		'border-foreground/12 bg-foreground/4 text-foreground/90 placeholder:text-foreground/35 min-h-10 w-full min-w-0 rounded-xl border px-3 py-2 outline-none transition-colors duration-150 focus:border-[color-mix(in_oklch,var(--accent-primary)_48%,transparent)] focus:bg-foreground/6 disabled:cursor-not-allowed disabled:opacity-55'
	const actionButtonClass =
		'rounded-pill inline-flex min-h-9 cursor-pointer items-center justify-center gap-1.5 px-4 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
</script>

<BaseModal
	{open}
	title="chat properties"
	description="title, tags, and access"
	onClose={() => !isSaving && onClose()}
	widthClassName="max-w-lg"
>
	{#if thread}
		<form class="grid gap-3" style={chatAccentStyle} onsubmit={handleSubmit}>
			<section class="{panelClass} flex min-w-0 items-center gap-4 rounded-[18px] border p-4">
				<div
					class="flex h-11 w-11 shrink-0 items-center justify-center rounded-[15px] border border-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_12%,transparent)] text-(--accent-primary)"
				>
					<ChatIcon variant="solid" class="h-5 w-5" />
				</div>
				<div class="min-w-0 flex-1">
					<p class="text-foreground/50 text-xs font-medium tracking-[0.12em] uppercase">
						{thread.is_temporary ? 'temporary chat' : 'chat'}
					</p>
					<h3 class="text-foreground min-w-0 truncate text-lg font-semibold">
						{displayTitle(title)}
					</h3>
					<p class="text-foreground/55 mt-0.5 min-w-0 truncate text-xs">
						{previewSubtitle}
					</p>
				</div>
			</section>

			<div class={fieldClass}>
				<ChatIcon variant="solid" class="h-4 w-4 text-(--accent-primary)" />
				<label class="text-foreground/60 text-[0.78rem] font-semibold" for="chat-title">
					title
				</label>
				<input
					id="chat-title"
					class="{inputClass} col-span-full"
					bind:value={title}
					placeholder="new chat"
					disabled={isSaving || !canEditThread}
				/>
			</div>

			<div class={fieldClass}>
				<Tag class="h-4 w-4 text-(--accent-primary)" />
				<label class="text-foreground/60 text-[0.78rem] font-semibold" for="chat-tags">
					tags
				</label>
				<TagEditor
					inputId="chat-tags"
					bind:value={tags}
					disabled={isSaving || !canEditThread}
				/>
			</div>

			<div class={fieldClass}>
				<Sparkles class="h-4 w-4 text-(--accent-primary)" />
				<label class="text-foreground/60 text-[0.78rem] font-semibold" for="chat-summary">
					summary
				</label>
				<div
					id="chat-summary"
					class="text-foreground/72 col-span-full min-h-10 rounded-xl px-1 py-1 text-sm leading-6 wrap-break-word whitespace-pre-wrap"
				>
					{#if isLoadingSummary}
						<ShimmerText className="inline-block">loading summary</ShimmerText>
					{:else if latestCatalogSummary?.content.trim()}
						{latestCatalogSummary.content.trim()}
					{:else}
						<span class="text-foreground/42">no summary yet</span>
					{/if}
				</div>
			</div>

			{#if error}
				<div
					class="rounded-container border-foreground/10 bg-foreground/5 text-foreground/70 border px-3 py-2 text-sm"
				>
					{error}
				</div>
			{/if}

			<div class="flex items-center gap-2 pt-1 max-[520px]:flex-wrap">
				{#if canGenerateMetadata}
					<button
						type="button"
						class="{actionButtonClass} border-foreground/12 text-foreground/80 hover:bg-foreground/6 border bg-transparent"
						disabled={isSaving || isGeneratingMetadata}
						onclick={() => void generateMetadata()}
					>
						<Sparkles class="h-4 w-4" />
						{#if isGeneratingMetadata}<ShimmerText className="inline-block"
								>generating</ShimmerText
							>{:else}<span>generate missing data</span>{/if}
					</button>
				{/if}
				{#if thread}
					<button
						type="button"
						class="{actionButtonClass} border-foreground/12 text-foreground/80 hover:bg-foreground/6 border bg-transparent"
						disabled={isSaving}
						onclick={onShare}
					>
						<Share class="h-4 w-4" />
						<span>share</span>
					</button>
				{/if}
				<div class="flex-1"></div>
				{#if canEditThread}
					<button
						type="submit"
						class="{actionButtonClass} bg-(--accent-primary) text-white hover:brightness-[1.06]"
						disabled={isSaving}
					>
						<Check class="h-4 w-4" />
						{#if isSaving}<ShimmerText className="inline-block">saving</ShimmerText
							>{:else}<span>save</span>{/if}
					</button>
				{/if}
			</div>
		</form>
	{:else}
		<div class="text-foreground/65 text-sm">chat not found</div>
	{/if}
</BaseModal>
