<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import NotesSidebar from '$lib/components/notes/NotesSidebar.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { notes } from '$lib/stores/notes.svelte'

	notes.hydrate()

	async function createNote() {
		const created = notes.create()
		await goto(resolve(`/notes/${created.id}`), { keepFocus: true, noScroll: true })
	}
</script>

{#if device.isMobile}
	<NotesSidebar selectedNoteId={null} isMobile={true} />
{:else}
	<div class="mx-auto mt-10 max-w-3xl">
		<div class="rounded-container border border-white/10 bg-white/5 p-6">
			<div class="text-lg font-semibold text-white/90">notes</div>
			<div class="mt-2 text-sm text-white/60">
				select a note on the left, or create a new one
			</div>
			<button
				type="button"
				onclick={createNote}
				class="rounded-pill mt-5 border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white/80 transition-colors hover:bg-white/8"
			>
				new note
			</button>
		</div>
	</div>
{/if}
