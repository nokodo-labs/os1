<script lang="ts">
	/**
	 * the typing bubble: three dots where the next incoming message will land,
	 * with the face of whoever is composing beside it. several composers share
	 * one bubble and stack their faces, the way a group thread reads in iMessage.
	 */

	import ConversationAvatar from '$lib/components/messages/ConversationAvatar.svelte'
	import type { ConversationFace } from '$lib/utils/conversationDisplay'

	interface Props {
		/** people composing right now: other humans only, never you, never agents */
		composers: ConversationFace[]
		/**
		 * whose typing it is. a group needs the faces; a DM does not - every
		 * incoming bubble there is already the one other person.
		 */
		showFaces?: boolean
		class?: string
	}

	let { composers, showFaces = true, class: className = '' }: Props = $props()

	/** past a few faces the stack stops reading; the rest are named in the label. */
	const AVATAR_LIMIT = 3
	const shownFaces = $derived(composers.slice(0, AVATAR_LIMIT))
	const isStacked = $derived(shownFaces.length > 1)

	const label = $derived.by(() => {
		const names = composers.map((face) => face.label)
		if (names.length === 0) return ''
		if (names.length === 1) return `${names[0]} is typing`
		if (names.length === 2) return `${names[0]} and ${names[1]} are typing`
		return `${names[0]}, ${names[1]} and ${names.length - 2} others are typing`
	})
</script>

{#if composers.length > 0}
	<div
		class="flex items-end gap-2 {className}"
		aria-live="polite"
		aria-label={label}
		data-typing-indicator
	>
		{#if showFaces}
			<div class="flex shrink-0 items-end -space-x-2">
				{#each shownFaces as face (face.id)}
					<div class="ring-card/80 rounded-full" class:ring-2={isStacked}>
						<ConversationAvatar
							faces={[face]}
							isGroup={false}
							sizeClass="size-8"
							textClass="text-xs"
						/>
					</div>
				{/each}
			</div>
		{/if}
		<!-- the incoming bubble's own surface: neutral tint over a heavy blur -->
		<div
			class="bg-foreground/10 flex items-center rounded-3xl px-3.5 py-3 backdrop-blur-[40px] [backdrop-saturate:180%]"
		>
			<span class="typing-dots text-foreground/70" aria-hidden="true">
				<span class="typing-dot"></span>
				<span class="typing-dot"></span>
				<span class="typing-dot"></span>
			</span>
		</div>
	</div>
{/if}

<style>
	.typing-dots {
		display: inline-flex;
		align-items: center;
		gap: 4px;
	}

	.typing-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: currentColor;
		opacity: 0.4;
		animation: typing-bounce 1.4s ease-in-out infinite;
	}

	.typing-dot:nth-child(2) {
		animation-delay: 0.2s;
	}

	.typing-dot:nth-child(3) {
		animation-delay: 0.4s;
	}

	@keyframes typing-bounce {
		0%,
		60%,
		100% {
			transform: translateY(0);
			opacity: 0.4;
		}
		30% {
			transform: translateY(-4px);
			opacity: 1;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.typing-dot {
			animation: none;
			opacity: 0.6;
		}
	}
</style>
