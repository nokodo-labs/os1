<script lang="ts">
	import type { Snippet } from 'svelte'
	import type { HTMLButtonAttributes } from 'svelte/elements'

	type Size = 'sm' | 'md' | 'lg'
	type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

	interface ActionButtonProps extends Omit<HTMLButtonAttributes, 'class'> {
		size?: Size
		variant?: Variant
		children: Snippet
		class?: string
	}

	let {
		size = 'md',
		variant = 'secondary',
		children,
		class: className = '',
		disabled,
		...rest
	}: ActionButtonProps = $props()

	const sizeClasses: Record<Size, string> = {
		sm: 'px-3 py-1.5 text-xs rounded-lg',
		md: 'px-4 py-2 text-sm rounded-xl',
		lg: 'px-5 py-2.5 text-base rounded-xl',
	}

	const variantClasses: Record<Variant, string> = {
		primary:
			'bg-[var(--accent-primary)] text-white hover:brightness-110 border border-transparent',
		secondary:
			'bg-white/10 text-white/90 hover:bg-white/15 hover:text-white border border-white/10 hover:border-white/15',
		ghost: 'bg-transparent text-white/80 hover:bg-white/8 hover:text-white border border-transparent',
		danger: 'bg-red-500/80 text-white hover:bg-red-500 border border-transparent',
	}

	const baseClasses =
		'inline-flex cursor-pointer items-center justify-center gap-2 font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 active:scale-[0.97] disabled:pointer-events-none disabled:opacity-40'
</script>

<button
	type="button"
	class="{baseClasses} {sizeClasses[size]} {variantClasses[variant]} {className}"
	{disabled}
	{...rest}
>
	{@render children()}
</button>

<style>
	button {
		-webkit-tap-highlight-color: transparent;
	}
</style>
