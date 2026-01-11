<script lang="ts">
	let {
		active = true,
		durationSeconds = 1.8,
		className = '',
		children,
	} = $props<{
		active?: boolean
		durationSeconds?: number
		className?: string
		children?: () => unknown
	}>()

	const styleVars = $derived.by(() => {
		const duration = Math.max(0.2, Math.min(30, durationSeconds))
		return `--shimmer-duration: ${duration}s;`
	})

	const shimmerClass = $derived.by(() => (active ? 'shimmer' : ''))
</script>

<span class={`${shimmerClass} ${className}`} style={active ? styleVars : ''}>
	{@render children?.()}
</span>
