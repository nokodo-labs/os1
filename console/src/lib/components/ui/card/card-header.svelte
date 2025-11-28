<script lang="ts">
	import { cn } from "$lib/utils";
	import type { HTMLAttributes } from "svelte/elements";

	let {
		class: className,
		children,
		...rest
	}: HTMLAttributes<HTMLDivElement> = $props();
</script>

<div class={cn("flex flex-col space-y-1.5 p-6", className)} {...rest}>
	{@render children?.()}
</div>
