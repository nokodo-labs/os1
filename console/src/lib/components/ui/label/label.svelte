<script lang="ts">
	import { cn } from "$lib/utils";
	import { Label as LabelPrimitive } from "bits-ui";

	let {
		class: className,
		children,
		...rest
	}: LabelPrimitive.RootProps = $props();
</script>

<LabelPrimitive.Root
	class={cn(
		"text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
		className,
	)}
	{...rest}
>
	{@render children?.()}
</LabelPrimitive.Root>
