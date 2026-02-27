<!--
	tiny dot overlay for WS connection health.
	green (pulsing) = connected, amber (pulsing) = connecting/reconnecting, red = disconnected.
	placed absolutely at the bottom-right circumference of the user avatar,
	matching the open-webui Sidebar pattern (center of dot sits on the circle edge).
-->
<script lang="ts">
	import type { ConnectionStatus } from '$lib/api/streaming/eventStream.svelte'

	interface ConnectionIndicatorProps {
		status: ConnectionStatus
	}

	const { status }: ConnectionIndicatorProps = $props()

	const colorMap: Record<ConnectionStatus, { bg: string; ping: string }> = {
		connected: { bg: 'bg-emerald-500', ping: 'bg-emerald-400' },
		connecting: { bg: 'bg-amber-500', ping: 'bg-amber-400' },
		reconnecting: { bg: 'bg-amber-500', ping: 'bg-amber-400' },
		disconnected: { bg: 'bg-red-500', ping: 'bg-red-400' },
	}

	const colors = $derived(colorMap[status])
	const shouldPulse = $derived(status !== 'disconnected')
</script>

<div
	class="ws-indicator pointer-events-none absolute z-10"
	role="status"
	aria-label="connection {status}"
>
	<span class="ws-indicator-dot relative flex">
		{#if shouldPulse}
			<span
				class="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 {colors.ping}"
			></span>
		{/if}
		<span
			class="ws-indicator-dot relative inline-flex rounded-full border-2 border-foreground/20 {colors.bg}"
		></span>
	</span>
</div>

<style>
	.ws-indicator {
		--indicator-size: 0.625rem;
		--avatar-size: 2.5rem;
		bottom: calc(
			(var(--avatar-size) / 2) - (var(--avatar-size) / 2 / 1.4142) -
				(var(--indicator-size) / 2)
		);
		right: calc(
			(var(--avatar-size) / 2) - (var(--avatar-size) / 2 / 1.4142) -
				(var(--indicator-size) / 2)
		);
	}

	.ws-indicator-dot {
		width: var(--indicator-size);
		height: var(--indicator-size);
	}
</style>
