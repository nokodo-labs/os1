<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import NoteEditor from '$lib/components/notes/NoteEditor.svelte'

	const noteId = $derived(page.params.id)

	const handleBackToNotes = async () => {
		await goto(resolve('/notes'), { keepFocus: true, noScroll: true })
	}
</script>

{#if noteId}
	{#key noteId}
		<NoteEditor {noteId} onBack={handleBackToNotes} />
	{/key}
{:else}
	<div class="mx-auto mt-10 max-w-3xl">
		<div class="rounded-container border border-foreground/10 bg-foreground/5 p-5 text-sm text-foreground/70">
			missing note id
		</div>
	</div>
{/if}
