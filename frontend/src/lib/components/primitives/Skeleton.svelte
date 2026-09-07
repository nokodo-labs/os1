<script lang="ts">
	// quiet frosted placeholders shaped like the content that is loading.
	// the caller owns the container (grid, stack, gaps); this renders `count` siblings.

	type SkeletonShape =
		| 'block'
		| 'card'
		| 'row'
		| 'pill'
		| 'tile'
		| 'lines'
		| 'avatar'
		| 'bubble'
		| 'gridCell'

	type SkeletonRadius = 'sm' | 'md' | 'lg' | 'xl' | 'container' | 'pill' | 'circle'

	interface Props {
		shape?: SkeletonShape
		count?: number
		width?: string
		height?: string
		radius?: SkeletonRadius
		lines?: number
		avatar?: boolean
		trailing?: boolean
		align?: 'start' | 'end'
		class?: string
	}

	let {
		shape = 'block',
		count = 1,
		width,
		height,
		radius,
		lines,
		avatar = true,
		trailing = false,
		align = 'start',
		class: className = '',
	}: Props = $props()

	const radiusClasses: Record<SkeletonRadius, string> = {
		sm: 'rounded-lg',
		md: 'rounded-xl',
		lg: 'rounded-2xl',
		xl: 'rounded-3xl',
		container: 'rounded-container',
		pill: 'rounded-pill',
		circle: 'rounded-circle',
	}

	const shapeRadius: Record<SkeletonShape, SkeletonRadius> = {
		block: 'lg',
		card: 'lg',
		row: 'lg',
		pill: 'pill',
		tile: 'container',
		lines: 'pill',
		avatar: 'circle',
		bubble: 'xl',
		gridCell: 'md',
	}

	const shapeSize: Record<SkeletonShape, string> = {
		block: 'h-16 w-full',
		card: 'h-80 w-full',
		row: 'h-16 w-full',
		pill: 'h-12 w-full',
		tile: 'w-full',
		lines: 'w-full',
		avatar: 'size-10',
		bubble: 'w-fit max-w-[72%] min-w-32',
		gridCell: 'h-full min-h-16 w-full',
	}

	const glass = 'liquid-glass liquid-glass--frosted overflow-hidden'
	const fill = 'bg-foreground/10'

	const items = $derived(Array.from({ length: Math.max(0, count) }, (_, i) => i))
	const lineCount = $derived(lines ?? (shape === 'lines' ? 3 : 2))
	const lineItems = $derived(Array.from({ length: Math.max(0, lineCount) }, (_, i) => i))
	const radiusClass = $derived(radiusClasses[radius ?? shapeRadius[shape]])
	const sizeStyle = $derived(
		`${width ? `width: ${width};` : ''}${height ? `height: ${height};` : ''}`
	)

	// varied widths so a stack of lines reads as text, not as bars
	function lineWidth(index: number, total: number): string {
		if (shape === 'row') return index === 0 ? '40%' : index === 1 ? '62%' : '30%'
		if (index === total - 1) return '58%'
		return index % 2 === 0 ? '100%' : '84%'
	}
</script>

{#snippet textLine(index: number, tall: boolean)}
	<div
		class="{fill} rounded-pill {tall ? 'h-3.5' : 'h-3'}"
		style="width: {lineWidth(index, lineCount)};"
	></div>
{/snippet}

{#each items as item (item)}
	{#if shape === 'row'}
		<div
			class="skeleton-item {glass} {radiusClass} {shapeSize[
				shape
			]} flex animate-pulse items-center gap-3 px-4 {className}"
			style={sizeStyle}
			data-skeleton={shape}
			aria-hidden="true"
		>
			{#if avatar}
				<div class="{fill} rounded-circle size-10 shrink-0"></div>
			{/if}
			<div class="flex min-w-0 flex-1 flex-col gap-2">
				{#each lineItems as line (line)}
					{@render textLine(line, line === 0)}
				{/each}
			</div>
			{#if trailing}
				<div class="{fill} rounded-pill h-6 w-16 shrink-0"></div>
			{/if}
		</div>
	{:else if shape === 'lines'}
		<div
			class="skeleton-item {shapeSize[shape]} flex animate-pulse flex-col gap-2 {className}"
			style={sizeStyle}
			data-skeleton={shape}
			aria-hidden="true"
		>
			{#each lineItems as line (line)}
				{@render textLine(line, false)}
			{/each}
		</div>
	{:else if shape === 'bubble'}
		<div
			class="skeleton-item {glass} {radiusClass} {shapeSize[shape]} {align === 'end'
				? 'ml-auto'
				: 'mr-auto'} flex animate-pulse flex-col gap-2 px-4 py-3 {className}"
			style={sizeStyle}
			data-skeleton={shape}
			aria-hidden="true"
		>
			{#each lineItems as line (line)}
				{@render textLine(line, false)}
			{/each}
		</div>
	{:else if shape === 'tile'}
		<div
			class="skeleton-item {shapeSize[
				shape
			]} flex animate-pulse flex-col items-center gap-2 {className}"
			data-skeleton={shape}
			aria-hidden="true"
		>
			<div class="{glass} {radiusClass} aspect-square w-full" style={sizeStyle}></div>
			<div class="{fill} rounded-pill h-3 w-3/5"></div>
		</div>
	{:else}
		<div
			class="skeleton-item {glass} {radiusClass} {shapeSize[shape]} animate-pulse {className}"
			style={sizeStyle}
			data-skeleton={shape}
			aria-hidden="true"
		></div>
	{/if}
{/each}

<style>
	/* same motion contract as the island and the tab scaffold */
	@media (prefers-reduced-motion: reduce) {
		.skeleton-item {
			animation: none;
		}
	}
</style>
