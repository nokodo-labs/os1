<script lang="ts">
	import type { SVGAttributes } from 'svelte/elements'

	interface IconProps extends Omit<SVGAttributes<SVGSVGElement>, 'class'> {
		value?: string
		class?: string
		color?: string
		strokeWidth?: string | number
	}

	type SortKind = 'alpha' | 'created' | 'updated' | 'manual' | 'length' | 'generic'
	type SortDirection = 'asc' | 'desc'

	let {
		value = '',
		class: className = 'size-4',
		color = 'currentColor',
		strokeWidth = '1.7',
		...rest
	}: IconProps = $props()

	const normalized = $derived(value.toLowerCase())
	const hasValue = $derived(normalized.trim().length > 0)
	const kind = $derived.by((): SortKind => {
		if (normalized.includes('position')) return 'manual'
		if (normalized.includes('content_length')) return 'length'
		if (normalized === 'name' || normalized.includes('title') || normalized.includes('name')) {
			return 'alpha'
		}
		if (
			normalized.includes('created_at') ||
			normalized === 'newest' ||
			normalized === 'oldest'
		) {
			return 'created'
		}
		if (normalized.includes('updated_at') || normalized.includes('last_activity_at')) {
			return 'updated'
		}
		return 'generic'
	})

	const direction = $derived.by((): SortDirection => {
		if (
			normalized.endsWith(':asc') ||
			normalized.endsWith('-asc') ||
			normalized === 'oldest' ||
			normalized === 'name'
		) {
			return 'asc'
		}
		return 'desc'
	})

	const alphaTop = $derived(direction === 'desc' ? 'z' : 'a')
	const alphaBottom = $derived(direction === 'desc' ? 'a' : 'z')
	const arrowPath = $derived(
		direction === 'asc' ? 'M19 17V3m0 0-3 3m3-3 3 3' : 'M19 3v14m0 0-3-3m3 3 3-3'
	)
</script>

{#if !hasValue}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill="none"
		stroke={color}
		stroke-width={strokeWidth}
		stroke-linecap="round"
		stroke-linejoin="round"
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<path d="M7 18V6m0 0L4 9m3-3 3 3" />
		<path d="M17 6v12m0 0-3-3m3 3 3-3" />
	</svg>
{:else}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 20"
		fill="none"
		stroke={color}
		stroke-width={strokeWidth}
		stroke-linecap="round"
		stroke-linejoin="round"
		class={className}
		aria-hidden="true"
		{...rest}
	>
		{#if kind === 'alpha'}
			<text x="3" y="8" fill={color} stroke="none" font-size="7" font-weight="700"
				>{alphaTop}</text
			>
			<text x="3" y="16" fill={color} stroke="none" font-size="7" font-weight="700"
				>{alphaBottom}</text
			>
		{:else if kind === 'created'}
			<path d="M4.5 3.5v2M10.5 3.5v2" />
			<path d="M3 7h9" />
			<rect x="2.5" y="5" width="11" height="11" rx="2" />
		{:else if kind === 'updated'}
			<circle cx="8" cy="10" r="5" />
			<path d="M8 7.5V10l2.25 1.35" />
		{:else if kind === 'manual'}
			<path d="M3 5.5h9M3 10h7M3 14.5h9" />
		{:else if kind === 'length'}
			{#if direction === 'asc'}
				<path d="M3 5.5h4M3 10h7M3 14.5h10" />
			{:else}
				<path d="M3 5.5h10M3 10h7M3 14.5h4" />
			{/if}
		{:else}
			<path d="M3 5.5h8M3 10h10M3 14.5h6" />
		{/if}
		<path d={arrowPath} />
	</svg>
{/if}
