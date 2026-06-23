<script lang="ts">
	import Cloud from '$lib/components/icons/Cloud.svelte'
	import Computer from '$lib/components/icons/Computer.svelte'
	import DevicePhone from '$lib/components/icons/DevicePhone.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type { ClientPreferenceScope } from '$lib/stores/preferences.svelte'

	interface Props {
		scope: ClientPreferenceScope
		onchange: (scope: ClientPreferenceScope) => void
		class?: string
	}

	let { scope, onchange, class: className = '' }: Props = $props()
</script>

<div
	class="rounded-pill border-foreground/10 bg-foreground/5 grid shrink-0 grid-cols-2 border p-1 {className}"
>
	<button
		type="button"
		aria-pressed={scope === 'synced'}
		onclick={() => onchange('synced')}
		class="rounded-pill flex h-8 cursor-pointer items-center justify-center gap-2 px-3 text-xs font-medium transition-colors {scope ===
		'synced'
			? 'bg-foreground/15 text-foreground'
			: 'text-foreground/55 hover:text-foreground'}"
	>
		<Cloud class="size-4" />
		<span>all devices</span>
	</button>
	<button
		type="button"
		aria-pressed={scope === 'client'}
		onclick={() => onchange('client')}
		class="rounded-pill flex h-8 cursor-pointer items-center justify-center gap-2 px-3 text-xs font-medium transition-colors {scope ===
		'client'
			? 'bg-foreground/15 text-foreground'
			: 'text-foreground/55 hover:text-foreground'}"
	>
		{#if device.isMobile}
			<DevicePhone class="size-4" />
		{:else}
			<Computer class="size-4" />
		{/if}
		<span>this device</span>
	</button>
</div>
