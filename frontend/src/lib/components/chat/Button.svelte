<script lang="ts">
	import type { Snippet } from 'svelte'

	interface Props {
		variant?: 'primary' | 'secondary' | 'ghost' | 'glass'
		size?: 'sm' | 'md' | 'lg' | 'icon'
		disabled?: boolean
		onclick?: () => void
		children: Snippet
	}

	let {
		variant = 'secondary',
		size = 'md',
		disabled = false,
		onclick,
		children,
	}: Props = $props()

	const sizeClasses: Record<string, string> = {
		sm: 'px-3 py-1.5 text-sm rounded-xl',
		md: 'px-4 py-2 text-[0.9375rem] rounded-xl',
		lg: 'px-6 py-3 text-base rounded-xl',
		icon: 'h-8 w-8 rounded-full p-0',
	}

	const variantClasses: Record<string, string> = {
		primary:
			'bg-linear-to-br from-[rgba(139,92,246,0.8)] to-[rgba(99,102,241,0.7)] text-white/95 shadow-[0_4px_20px_rgba(139,92,246,0.3)] hover:not(:disabled):-translate-y-0.5 hover:not(:disabled):shadow-[0_8px_32px_rgba(139,92,246,0.4)]',
		secondary:
			'bg-linear-to-br from-white/15 to-white/5 text-white/90 hover:not(:disabled):from-white/20 hover:not(:disabled):to-white/10 hover:not(:disabled):-translate-y-0.5',
		ghost: 'bg-transparent text-white/70 hover:not(:disabled):bg-white/10 hover:not(:disabled):text-white/95',
		glass: 'text-white/70 hover:not(:disabled):text-white/95',
	}
</script>

{#if variant === 'glass'}
	<button
		class="liquid-glass active:not(:disabled):scale-[0.98] relative inline-flex cursor-pointer items-center justify-center gap-2 overflow-hidden border-none font-medium transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] disabled:cursor-not-allowed disabled:opacity-50 {sizeClasses[
			size
		]} {variantClasses[variant]}"
		{disabled}
		{onclick}
	>
		<span class="liquid-glass__highlight" aria-hidden="true"></span>
		<span class="liquid-glass__content">
			{@render children()}
		</span>
	</button>
{:else}
	<button
		class="active:not(:disabled):translate-y-0 active:not(:disabled):scale-[0.98] relative inline-flex cursor-pointer items-center justify-center gap-2 overflow-hidden border-none font-medium backdrop-blur-[10px] transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:bg-linear-to-br before:from-white/30 before:to-white/10 before:mask-exclude before:p-px before:opacity-0 before:transition-opacity before:duration-300 before:content-[''] before:[-webkit-mask-composite:xor] before:[-webkit-mask:linear-gradient(#fff_0_0)_content-box,linear-gradient(#fff_0_0)] before:[mask:linear-gradient(#fff_0_0)_content-box,linear-gradient(#fff_0_0)] hover:before:opacity-100 disabled:cursor-not-allowed disabled:opacity-50 {sizeClasses[
			size
		]} {variantClasses[variant]}"
		{disabled}
		{onclick}
	>
		{@render children()}
	</button>
{/if}
