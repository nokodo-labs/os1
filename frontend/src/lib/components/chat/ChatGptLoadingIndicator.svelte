<script lang="ts">
	export type ChatGptLoadingIndicatorSize = 'xs' | 'sm' | 'md'

	interface Props {
		size?: ChatGptLoadingIndicatorSize
		className?: string
	}

	let { size = 'md', className = '' }: Props = $props()

	const sizeClass = $derived(size === 'xs' ? 'size-1.5' : size === 'sm' ? 'size-2' : 'size-3')
	const dotClass = $derived(size === 'xs' ? 'size-1.5' : size === 'sm' ? 'size-2' : 'size-3')
</script>

<span
	class={`relative inline-flex align-middle ${sizeClass} ${className}`.trim()}
	aria-hidden="true"
>
	<span class="absolute inline-flex h-full w-full animate-pulse rounded-full bg-foreground/20"></span>
	<span class={`relative inline-flex rounded-full bg-foreground/70 ${dotClass} chatgpt-dot`}></span>
</span>

<style>
	@keyframes chatgpt_dot_scale {
		0%,
		100% {
			transform: scale(1);
		}
		50% {
			transform: scale(1.25);
		}
	}

	.chatgpt-dot {
		animation: chatgpt_dot_scale 1.5s ease-in-out infinite;
	}
</style>
