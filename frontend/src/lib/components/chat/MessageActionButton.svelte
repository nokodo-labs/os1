<script lang="ts">
	import type { Snippet } from 'svelte'

	interface Props {
		onclick: () => void
		ariaLabel: string
		children: Snippet
	}

	let { onclick, ariaLabel, children }: Props = $props()
</script>

<button
	type="button"
	class="text-foreground/80 hover:text-foreground flex h-6 w-6 cursor-pointer items-center justify-center transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97]"
	{onclick}
	aria-label={ariaLabel}
>
	{@render children()}
</button>
