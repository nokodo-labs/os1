<script lang="ts">
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'

	let promptName = $state('')
	let promptText = $state('')
</script>

<div class="space-y-6">
	<div>
		<h2 class="text-2xl font-bold tracking-tight">prompts</h2>
		<p class="text-zinc-400">write and iterate on prompts.</p>
	</div>

	<div class="rounded-2xl border border-amber-900/50 bg-amber-900/10 p-4 text-sm text-amber-200">
		prompts are not exposed in the backend openapi yet, so this page is currently local-only.
	</div>

	<Card class="rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
		<CardHeader>
			<CardTitle>draft</CardTitle>
			<CardDescription>use this as a scratchpad until the API is ready.</CardDescription>
		</CardHeader>
		<CardContent class="space-y-4">
			<div class="space-y-2">
				<Label for="name">name</Label>
				<Input
					id="name"
					bind:value={promptName}
					placeholder="e.g. summarize meeting notes"
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<Label for="prompt">prompt</Label>
				<textarea
					id="prompt"
					bind:value={promptText}
					rows={14}
					placeholder="write your prompt..."
					class="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-sm"
				></textarea>
			</div>
			<div class="flex justify-end">
				<Button
					variant="outline"
					class="rounded-xl"
					disabled
					title="API not implemented yet"
				>
					save
				</Button>
			</div>
		</CardContent>
	</Card>
</div>
