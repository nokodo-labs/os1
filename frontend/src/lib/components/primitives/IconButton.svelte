<script lang="ts">
	import type { Snippet } from 'svelte'
	import type { HTMLButtonAttributes } from 'svelte/elements'

	type Size = 'xs' | 'sm' | 'md' | 'lg'
	type Variant = 'ghost' | 'subtle' | 'solid'

	interface IconButtonProps extends Omit<HTMLButtonAttributes, 'class'> {
		size?: Size
		variant?: Variant
		children: Snippet
		class?: string
	}

	let {
		size = 'md',
		variant = 'ghost',
		children,
		class: className = '',
		disabled,
		...rest
	}: IconButtonProps = $props()

	const sizeClasses: Record<Size, string> = {
		xs: 'h-6 w-6',
		sm: 'h-8 w-8',
		md: 'h-10 w-10',
		lg: 'h-12 w-12',
	}

	const iconSizeClasses: Record<Size, string> = {
		xs: '[&>*]:h-3.5 [&>*]:w-3.5',
		sm: '[&>*]:h-4 [&>*]:w-4',
		md: '[&>*]:h-5 [&>*]:w-5',
		lg: '[&>*]:h-6 [&>*]:w-6',
	}

	const variantClasses: Record<Variant, string> = {
		ghost: 'bg-transparent text-white/70 hover:text-white hover:bg-white/8',
		subtle: 'bg-white/5 text-white/80 hover:bg-white/12 hover:text-white',
		solid: 'bg-white/15 text-white hover:bg-white/22',
	}

	const baseClasses =
		'inline-flex cursor-pointer items-center justify-center rounded-pill border-none transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 active:scale-[0.94] disabled:pointer-events-none disabled:opacity-40'
</script>

<button
	type="button"
	class="{baseClasses} {sizeClasses[size]} {iconSizeClasses[size]} {variantClasses[
		variant
	]} {className}"
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
