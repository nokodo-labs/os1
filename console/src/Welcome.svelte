<script lang="ts">
	import { Button } from "$lib/components/ui/button";

	let { onStart }: { onStart: () => void } = $props();
</script>

<div
	class="flex min-h-screen flex-col items-center justify-center bg-zinc-950 text-center text-zinc-100"
>
	<div class="max-w-md space-y-6 p-6">
		<div class="space-y-2">
			<p class="text-sm uppercase tracking-[0.3em] text-zinc-400">
				nokodo
			</p>
			<h1 class="text-4xl font-bold tracking-tight">welcome</h1>
		</div>
		<p class="text-zinc-400">
			it looks like this is a fresh installation. let's set up your admin
			account to get started.
		</p>
		<Button size="lg" onclick={onStart}>create admin account</Button>
	</div>
</div>
