<script lang="ts">
	import { Select as SelectPrimitive } from "bits-ui";

	let { children, ...rest } = $props();
</script>

<SelectPrimitive.Root type="single" {...rest}>
	{@render children?.()}
</SelectPrimitive.Root>
