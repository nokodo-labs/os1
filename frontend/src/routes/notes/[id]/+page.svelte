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
	<NoteEditor {noteId} onBack={handleBackToNotes} />
{:else}
	<div class="mx-auto mt-10 max-w-3xl">
		<div class="rounded-container border border-white/10 bg-white/5 p-5 text-sm text-white/70">
			missing note id
		</div>
	</div>
{/if}
