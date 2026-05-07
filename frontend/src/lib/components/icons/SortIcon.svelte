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
		strokeWidth = '1.5',
		...rest
	}: IconProps = $props()

	const normalized = $derived(value.toLowerCase())
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
		if (normalized.endsWith(':asc') || normalized.endsWith('-asc') || normalized === 'oldest') {
			return 'asc'
		}
		return 'desc'
	})

	const alphaTop = $derived(direction === 'desc' ? 'z' : 'a')
	const alphaBottom = $derived(direction === 'desc' ? 'a' : 'z')
</script>

{#if kind === 'alpha'}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill="none"
		stroke={color}
		stroke-width={strokeWidth}
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<text x="4" y="9" fill={color} font-size="7" font-weight="700">{alphaTop}</text>
		<text x="4" y="19" fill={color} font-size="7" font-weight="700">{alphaBottom}</text>
		<path stroke-linecap="round" stroke-linejoin="round" d="M17 5v14m0 0-3-3m3 3 3-3" />
	</svg>
{:else if kind === 'created'}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill="none"
		stroke={color}
		stroke-width={strokeWidth}
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			d="M5.5 4.5v2M12 4.5v2m6.5-2v2M4 10h11M4.5 7h11A1.5 1.5 0 0 1 17 8.5V18a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 3 18V8.5A1.5 1.5 0 0 1 4.5 7Z"
		/>
		{#if direction === 'desc'}
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				d="M20 5v14m0 0-2.5-2.5M20 19l2.5-2.5"
			/>
		{:else}
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				d="M20 19V5m0 0-2.5 2.5M20 5l2.5 2.5"
			/>
		{/if}
	</svg>
{:else if kind === 'updated'}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill="none"
		stroke={color}
		stroke-width={strokeWidth}
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<path stroke-linecap="round" stroke-linejoin="round" d="M10.5 5a6.5 6.5 0 1 0 6.2 8.5" />
		<path stroke-linecap="round" stroke-linejoin="round" d="M10.5 8.5v4l3 1.75" />
		<path stroke-linecap="round" stroke-linejoin="round" d="M15.5 4.75h4v4" />
		<path stroke-linecap="round" stroke-linejoin="round" d="M19.25 4.75 15.5 8.5" />
		{#if direction === 'desc'}
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				d="M20 12v7m0 0-2.5-2.5M20 19l2.5-2.5"
			/>
		{:else}
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				d="M20 19v-7m0 0-2.5 2.5M20 12l2.5 2.5"
			/>
		{/if}
	</svg>
{:else if kind === 'manual'}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill="none"
		stroke={color}
		stroke-width={strokeWidth}
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			d="M3 5h10.5M3 10h8M3 15h5.5m5-.5 3.5-3.5m0 0 3.5 3.5M17 11v8"
		/>
	</svg>
{:else if kind === 'length'}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill="none"
		stroke={color}
		stroke-width={strokeWidth}
		class={className}
		aria-hidden="true"
		{...rest}
	>
		{#if direction === 'desc'}
			<path stroke-linecap="round" d="M4 6h10M4 12h7M4 18h4" />
		{:else}
			<path stroke-linecap="round" d="M4 6h4M4 12h7M4 18h10" />
		{/if}
		{#if direction === 'desc'}
			<path stroke-linecap="round" stroke-linejoin="round" d="M18 5v14m0 0-3-3m3 3 3-3" />
		{:else}
			<path stroke-linecap="round" stroke-linejoin="round" d="M18 19V5m0 0-3 3m3-3 3 3" />
		{/if}
	</svg>
{:else}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill="none"
		stroke={color}
		stroke-width={strokeWidth}
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<path stroke-linecap="round" stroke-linejoin="round" d="M7 4v10m0-10 3 3m-3-3L4 7" />
		<path stroke-linecap="round" stroke-linejoin="round" d="M17 20V10m0 10-3-3m3 3 3-3" />
	</svg>
{/if}
