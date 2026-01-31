<script lang="ts">
	let {
		active = true,
		durationSeconds = 1.8,
		className = '',
		textColor,
		waveColor,
		children,
	} = $props<{
		active?: boolean
		durationSeconds?: number
		className?: string
		textColor?: string
		waveColor?: string
		children?: () => unknown
	}>()

	const styleVars = $derived.by(() => {
		const duration = Math.max(0.2, Math.min(30, durationSeconds))
		const parts = [`--shimmer-duration: ${duration}s;`]
		if (textColor) parts.push(`--text-color: ${textColor};`)
		if (waveColor) parts.push(`--shimmer-wave-color: ${waveColor};`)
		return parts.join(' ')
	})

	const shimmerClass = $derived.by(() => (active ? 'shimmer' : ''))
</script>

<span class={`${shimmerClass} ${className}`} style={active ? styleVars : ''}>
	{@render children?.()}
</span>
