<script lang="ts">
	import TagEditor from '$lib/components/common/TagEditor.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Tag from '$lib/components/icons/Tag.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
	import type { Thread } from '$lib/stores/chat.svelte'
	import { canEditAccessLevel, resourceAccess } from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { byAuthor, metadataLine } from '$lib/utils/resourceAuthors'

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

	$effect(() => {
		const accessKey = open && thread ? `${thread.id}:${resourceAccess.version}` : ''
		if (open && thread?.owner_id && thread.owner_id !== session.currentUserId) {
			void session.ensureUsers([thread.owner_id])
		}
		if (open && thread && accessKey)
			void resourceAccess.ensure('thread', thread.id, thread.owner_id)
	})

	function displayTitle(value: string): string {
		const trimmed = value.trim()
		return trimmed || thread?.title || 'new chat'
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

			{#if error}
				<div
					class="rounded-container border-foreground/10 bg-foreground/5 text-foreground/70 border px-3 py-2 text-sm"
				>
					{error}
				</div>
			{/if}

			<div class="flex items-center gap-2 pt-1 max-[520px]:flex-wrap">
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
