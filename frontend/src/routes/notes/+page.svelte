<script lang="ts">
	import NotesSidebar from '$lib/components/notes/NotesSidebar.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { notes } from '$lib/stores/notes.svelte'

	$effect(() => {
		void notes.load()
	})
</script>

{#if device.isMobile}
	<NotesSidebar selectedNoteId={null} isMobile={true} />
{:else}
	<div
		class="flex h-[calc(100vh-var(--chrome-island-offset,0px)-var(--spacing-island-content)-2.5rem)] items-center justify-center"
	>
		<p class="text-sm text-white/50">select or create a note</p>
	</div>
{/if}
