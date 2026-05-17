<script lang="ts">
	import type { QueuedSteeringMessage } from '$lib/chat'
	import { contentPartsToText } from '$lib/chat/helpers'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import Clock from '$lib/components/icons/Clock.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import { SvelteSet } from 'svelte/reactivity'

	interface SteeringQueueProps {
		messages: QueuedSteeringMessage[]
		onDrop?: (runId: string, messageId: string) => Promise<void> | void
	}

	let { messages, onDrop }: SteeringQueueProps = $props()
	const dropping = new SvelteSet<string>()

	function textFor(message: QueuedSteeringMessage): string {
		const fromParts = contentPartsToText(message.content).trim()
		if (message.text.trim()) return message.text.trim()
		if (fromParts) return fromParts
		const filenames = message.attachments.map((attachment) => attachment.filename).join(', ')
		return filenames || 'queued message'
	}

	async function drop(message: QueuedSteeringMessage): Promise<void> {
		if (!onDrop || dropping.has(message.id)) return
		dropping.add(message.id)
		try {
			await onDrop(message.runId, message.id)
		} finally {
			dropping.delete(message.id)
		}
	}
</script>

{#if messages.length > 0}
	<div
		class="mb-3 flex max-h-[33vh] flex-col items-end gap-2 overflow-y-auto"
		aria-label="steering queue"
	>
		{#each messages as message (message.id)}
			<div
				class="flex max-w-[80%] animate-[queuedMessageIn_0.32s_cubic-bezier(0.34,1.56,0.64,1)] items-center justify-end gap-2"
			>
				<span
					class="text-foreground/55 flex size-4 shrink-0 items-center justify-center"
					aria-hidden="true"
				>
					<span class="clock-tick flex size-4 items-center justify-center">
						<Clock class="h-4 w-4" strokeWidth="2" />
					</span>
				</span>

				<LiquidGlass
					class="text-foreground/70 min-w-0 rounded-3xl px-3 py-2 opacity-75 backdrop-blur-[20px] [backdrop-saturate:180%]"
					style={`view-transition-name: steering-message-${message.id}; background-color: color-mix(in srgb, var(--accent-primary) 42%, var(--background) 58%); box-shadow: 0 4px 16px color-mix(in srgb, var(--accent-border) 55%, transparent);`}
				>
					<p class="min-w-0 truncate text-sm leading-relaxed whitespace-pre-wrap">
						{textFor(message)}
					</p>
				</LiquidGlass>

				<button
					type="button"
					class="liquid-glass text-foreground/45 hover:text-foreground flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40"
					aria-label="drop queued message"
					disabled={dropping.has(message.id)}
					onclick={() => drop(message)}
				>
					<XMark class="h-3.5 w-3.5" />
				</button>
			</div>
		{/each}
	</div>
{/if}

<style>
	@keyframes queuedMessageIn {
		from {
			opacity: 0;
			filter: blur(2px);
			transform: translateY(24px) scale(0.94);
		}
		to {
			opacity: 1;
			filter: blur(0);
			transform: translateY(0) scale(1);
		}
	}

	@keyframes queueClockTick {
		to {
			transform: rotate(360deg);
		}
	}

	.clock-tick {
		animation: queueClockTick 1.4s steps(12) infinite;
		transform-origin: center;
	}
</style>
