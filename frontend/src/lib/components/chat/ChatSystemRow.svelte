<script lang="ts">
	/**
	 * a centered, quiet row in the transcript: what HAPPENED to the chat rather
	 * than what anyone said. no bubble, no avatar, no actions - imessage renders
	 * these as plain grey text between the bubbles, and so do we.
	 *
	 * the copy arrives pre-resolved as segments so the names inside it can carry
	 * weight without the component knowing anything about participants.
	 */

	import type { SystemRowSegment } from '$lib/chat/systemEvents'

	interface Props {
		segments: SystemRowSegment[]
		/** the beginning-of-chat header, which opens the transcript rather than punctuating it. */
		header?: boolean
	}

	let { segments, header = false }: Props = $props()

	const label = $derived(segments.map((segment) => segment.text).join(''))
</script>

{#if segments.length > 0}
	<div
		class="flex justify-center px-6 {header ? 'pb-1' : 'py-1'}"
		data-chat-system-row
		aria-label={label}
	>
		<p class="text-foreground/45 max-w-sm text-center text-xs leading-snug text-balance">
			{#each segments as segment, index (index)}<span
					class={segment.strong ? 'text-foreground/60 font-medium' : undefined}
					>{segment.text}</span
				>{/each}
		</p>
	</div>
{/if}
