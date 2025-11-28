<script lang="ts">
	import { cn } from "$lib/utils";
	import type { HTMLAttributes } from "svelte/elements";

	let {
		class: className,
		children,
		...rest
	}: HTMLAttributes<HTMLDivElement> = $props();
</script>

<div class={cn("flex items-center p-6 pt-0", className)} {...rest}>
	{@render children?.()}
</div>
