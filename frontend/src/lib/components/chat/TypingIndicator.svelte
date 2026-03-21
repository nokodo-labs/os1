<script lang="ts">
	/**
	 * 3-dot iMessage-style typing indicator.
	 * shown when other users are typing in the current thread.
	 */

	interface Props {
		/** set of user IDs currently typing */
		typingUserIds: ReadonlySet<string>
		/** optional lookup to show names instead of "someone" */
		userNameById?: ReadonlyMap<string, string>
		class?: string
	}

	let { typingUserIds, userNameById, class: className = '' }: Props = $props()

	const isVisible = $derived(typingUserIds.size > 0)

	const label = $derived.by(() => {
		if (typingUserIds.size === 1) {
			const uid = [...typingUserIds][0]
			const name = userNameById?.get(uid) ?? 'someone'
			return `${name} is typing`
		}
		return 'others are typing'
	})
</script>

{#if isVisible}
	<div
		class="text-foreground/50 flex items-center gap-2 px-3 py-1.5 text-xs {className}"
		aria-live="polite"
		aria-label={label}
	>
		<span class="typing-dots" aria-hidden="true">
			<span class="typing-dot"></span>
			<span class="typing-dot"></span>
			<span class="typing-dot"></span>
		</span>
		<span class="select-none">{label}</span>
	</div>
{/if}

<style>
	.typing-dots {
		display: inline-flex;
		align-items: center;
		gap: 3px;
	}

	.typing-dot {
		width: 6px;
		height: 6px;
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
</style>
