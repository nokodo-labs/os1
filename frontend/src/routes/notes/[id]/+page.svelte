<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import NoteEditor from '$lib/components/notes/NoteEditor.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'

	const chrome = useSystemChrome()

	const noteId = $derived(page.params.id)

	const handleBackToNotes = async () => {
		await goto(resolve('/notes'), { keepFocus: true, noScroll: true })
	}

	$effect(() => {
		if (device.isMobile) {
			chrome.setContextActions(mobileBackAction)
			return () => chrome.setContextActions(null)
		}
	})
</script>

{#snippet mobileBackAction()}
	<button
		type="button"
		class="rounded-pill flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
		onclick={handleBackToNotes}
		aria-label="back to notes"
	>
		<ChevronLeft class="h-5 w-5" strokeWidth="2" />
	</button>
{/snippet}

{#if noteId}
	<NoteEditor {noteId} />
{:else}
	<div class="mx-auto mt-10 max-w-3xl">
		<div class="rounded-container border border-white/10 bg-white/5 p-5 text-sm text-white/70">
			missing note id
		</div>
	</div>
{/if}
