<script lang="ts">
	import TagEditor from '$lib/components/common/TagEditor.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Tag from '$lib/components/icons/Tag.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
	import { modals, type NotePropertiesPayload } from '$lib/stores/modals.svelte'
	import { notes } from '$lib/stores/notes.svelte'
	import {
		canEditAccessLevel,
		canShareAccessLevel,
		resourceAccess,
	} from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { byAuthor, metadataLine } from '$lib/utils/resourceAuthors'

	interface Props {
		open: boolean
		payload: NotePropertiesPayload | null
		onClose: () => void
	}

	let { open, payload, onClose }: Props = $props()

	let title = $state('')
	let labels = $state<string[]>([])
	let isSaving = $state(false)
	let error = $state<string | null>(null)

	const note = $derived(payload ? notes.get(payload.noteId) : null)
	const noteAccessLevel = $derived(
		note ? resourceAccess.level('note', note.id, note.userId) : null
	)
	const canEditNote = $derived(canEditAccessLevel(noteAccessLevel))
	const canShareNote = $derived(canShareAccessLevel(noteAccessLevel))
	const labelPreview = $derived(labels.join(', ') || 'no labels')
	const authorLabel = $derived(session.authorLabel(note?.userId))
	const previewSubtitle = $derived(metadataLine(byAuthor(authorLabel), labelPreview))
	const noteVisual = resourceVisual('note')
	const NoteIcon = noteVisual.icon
	const noteAccentStyle = resourceAccentStyle('note')

	$effect(() => {
		if (!open) return
		void notes.load()
	})

	$effect(() => {
		if (!open || !note) return
		title = note.title
		labels = [...note.labels]
		isSaving = false
		error = null
	})

	$effect(() => {
		if (open && note?.userId && note.userId !== session.currentUserId) {
			void session.ensureUsers([note.userId])
		}
		if (open && note) void resourceAccess.ensure('note', note.id, note.userId)
	})

	function displayTitle(value: string): string {
		const trimmed = value.trim()
		return trimmed || 'untitled note'
	}

	function shareNote(): void {
		if (!note || !canShareNote) return
		modals.open('resource-access', {
			resourceType: 'note',
			resourceId: note.id,
			title: displayTitle(title),
		})
	}

	async function save(): Promise<void> {
		if (!note || !canEditNote || isSaving) return
		isSaving = true
		error = null
		try {
			const saved = await notes.update(note.id, {
				title: title.trim(),
				labels,
			})
			if (!saved) return
			onClose()
		} catch {
			error = 'could not save note'
		} finally {
			isSaving = false
		}
	}

	function handleSubmit(event: SubmitEvent): void {
		event.preventDefault()
		void save()
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
	title="note properties"
	description="title, labels, and access"
	onClose={() => !isSaving && onClose()}
	widthClassName="max-w-lg"
>
	{#if note}
		<form class="grid gap-3" style={noteAccentStyle} onsubmit={handleSubmit}>
			<section class="{panelClass} flex min-w-0 items-center gap-4 rounded-[18px] border p-4">
				<div
					class="flex h-11 w-11 shrink-0 items-center justify-center rounded-[15px] border border-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_12%,transparent)] text-(--accent-primary)"
				>
					<NoteIcon variant="solid" class="h-5 w-5" />
				</div>
				<div class="min-w-0 flex-1">
					<p class="text-foreground/50 text-xs font-medium tracking-[0.12em] uppercase">
						note
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
				<NoteIcon variant="solid" class="h-4 w-4 text-(--accent-primary)" />
				<label class="text-foreground/60 text-[0.78rem] font-semibold" for="note-title">
					title
				</label>
				<input
					id="note-title"
					type="text"
					class="{inputClass} col-span-full"
					bind:value={title}
					placeholder="untitled note"
					disabled={isSaving || !canEditNote}
				/>
			</div>

			<div class={fieldClass}>
				<Tag class="h-4 w-4 text-(--accent-primary)" />
				<label class="text-foreground/60 text-[0.78rem] font-semibold" for="note-labels">
					labels
				</label>
				<TagEditor
					inputId="note-labels"
					bind:value={labels}
					disabled={isSaving || !canEditNote}
				/>
			</div>

			{#if error}
				<p class="text-destructive text-sm">{error}</p>
			{/if}

			<div class="flex items-center gap-2 pt-1 max-[520px]:flex-wrap">
				{#if canShareNote}
					<button
						type="button"
						class="{actionButtonClass} border-foreground/12 text-foreground/80 hover:bg-foreground/6 border bg-transparent"
						disabled={isSaving}
						onclick={shareNote}
					>
						<Share class="h-4 w-4" />
						<span>share</span>
					</button>
				{/if}
				<div class="flex-1"></div>
				{#if canEditNote}
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
		<div class="text-foreground/65 text-sm">note not found</div>
	{/if}
</BaseModal>
