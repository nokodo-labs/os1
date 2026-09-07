<script lang="ts">
	/** an agent's face: its image, or its initial when it has none or the image fails. */
	interface AgentAvatarProps {
		name: string
		avatarUrl?: string | null
		/** sizing for the round root; the fallback letter scales with `textClass`. */
		class?: string
		textClass?: string
	}

	let {
		name,
		avatarUrl = null,
		class: className = 'h-8 w-8',
		textClass = 'text-sm',
	}: AgentAvatarProps = $props()

	// a new url gets a fresh chance to load.
	let failed = $derived(!avatarUrl)
</script>

{#if avatarUrl && !failed}
	<img
		src={avatarUrl}
		alt={name}
		class="shrink-0 rounded-full object-cover {className}"
		onerror={() => (failed = true)}
	/>
{:else}
	<div
		class="bg-(--accent-primary) text-foreground/90 flex shrink-0 items-center justify-center rounded-full font-semibold uppercase {textClass} {className}"
		aria-label={name}
	>
		{name.charAt(0)}
	</div>
{/if}
