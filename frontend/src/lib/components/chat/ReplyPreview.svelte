<script lang="ts">
	import { contentPartsToText } from '$lib/chat/helpers'
	import { revealMessage } from '$lib/chat/messageFocus'
	import type { ApiMessage } from '$lib/chat/types'
	import XMark from '$lib/components/icons/XMark.svelte'

	interface Props {
		/** message being replied to; null once it is off the loaded branch. */
		message: ApiMessage | null
		/** who wrote it, already resolved by the caller. */
		authorName?: string | null
		/** target to jump to, for when the message itself is off the branch. */
		messageId?: string | null
		/** clicking the quote reveals its message. off in the composer. */
		jumpable?: boolean
		/** drop the reply while composing. */
		onDismiss?: () => void
		class?: string
	}

	let {
		message,
		authorName = null,
		messageId = null,
		jumpable = false,
		onDismiss,
		class: className = '',
	}: Props = $props()

	/** roughly the two lines the quote is clamped to. */
	const PREVIEW_LIMIT = 120

	const preview = $derived.by(() => {
		if (!message) return null
		const text = contentPartsToText(message.content).trim().replace(/\s+/g, ' ')
		if (text.length === 0) return null
		return text.length > PREVIEW_LIMIT ? `${text.slice(0, PREVIEW_LIMIT)}...` : text
	})

	// an attachment-only message still deserves a quote line
	const fallback = $derived(message ? 'attachment' : 'message unavailable')

	const targetId = $derived(messageId ?? message?.id ?? null)
	const canJump = $derived(jumpable && targetId !== null)
</script>

{#snippet body()}
	{#if authorName}
		<div class="text-foreground/70 truncate text-sm font-semibold">{authorName}</div>
	{/if}
	<div class="text-foreground/70 line-clamp-2 text-sm">{preview ?? fallback}</div>
{/snippet}

<div
	class="border-(--accent-primary)/40 bg-(--accent-primary)/8 flex items-center gap-1 overflow-hidden rounded-xl border-l-2 {className}"
>
	<!-- the quote area is the click target in full: a thin strip of text is a
	     miserable thing to aim at, especially on a touchscreen -->
	{#if canJump}
		<button
			type="button"
			class="hover:bg-foreground/5 min-w-0 flex-1 cursor-pointer px-3 py-2 text-left transition-colors"
			onclick={() => targetId && void revealMessage(targetId, { behavior: 'smooth' })}
		>
			{@render body()}
		</button>
	{:else}
		<div class="min-w-0 flex-1 px-3 py-2">{@render body()}</div>
	{/if}
	{#if onDismiss}
		<button
			type="button"
			class="text-muted-foreground hover:text-foreground flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center border-none bg-transparent transition-all duration-150 hover:scale-[1.05] active:scale-[0.97]"
			aria-label="cancel reply"
			onclick={onDismiss}
		>
			<XMark class="h-5 w-5" />
		</button>
	{/if}
</div>
