<script lang="ts">
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Switch } from '$lib/components/ui/switch'
	import { Lock } from '@lucide/svelte'

	type CodeInterpreterEngine = 'native' | 'e2b'

	type Props = {
		enabled?: boolean
		engine?: CodeInterpreterEngine
		e2bApiKey?: string
		e2bTemplate?: string
		e2bAvailablePackages?: string
		timeout?: string
	}

	let {
		enabled = $bindable(true),
		engine = $bindable<CodeInterpreterEngine>('e2b'),
		e2bApiKey = $bindable(''),
		e2bTemplate = $bindable(''),
		e2bAvailablePackages = $bindable(''),
		timeout = $bindable(''),
	}: Props = $props()
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>code interpreter</CardTitle>
		<CardDescription>sandbox engine for code execution in chat.</CardDescription>
	</CardHeader>
	<CardContent class="space-y-5">
		<div class="flex items-center justify-between">
			<div>
				<Label for="ci_enabled">enabled</Label>
				<p class="text-xs text-zinc-500">allow code execution in chat.</p>
			</div>
			<Switch
				id="ci_enabled"
				checked={enabled}
				onCheckedChange={(v: boolean) => (enabled = v)}
			/>
		</div>

		{#if enabled}
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="ci_engine">engine</Label>
					<p class="text-xs text-zinc-500">sandbox backend to use.</p>
					<Select
						value={engine}
						onValueChange={(v: string) => (engine = v as CodeInterpreterEngine)}
					>
						<SelectTrigger id="ci_engine" class="rounded-xl">
							<span class="truncate text-left">{engine}</span>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="native">native</SelectItem>
							<SelectItem value="e2b">e2b</SelectItem>
						</SelectContent>
					</Select>
				</div>

				<div class="space-y-2">
					<Label for="ci_timeout">timeout (seconds)</Label>
					<p class="text-xs text-zinc-500">max execution time per run (min 5).</p>
					<Input
						id="ci_timeout"
						type="number"
						min="5"
						bind:value={timeout}
						class="rounded-xl"
					/>
				</div>
			</div>

			{#if engine === 'e2b'}
				<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
					<p class="mb-4 text-sm font-medium">e2b settings</p>
					<div class="grid gap-4 md:grid-cols-2">
						<div class="space-y-2">
							<div class="flex items-center gap-2">
								<Label for="ci_e2b_api_key">api key</Label>
								<span
									class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
								>
									<Lock class="h-3 w-3" />
									sensitive
								</span>
							</div>
							<Input
								id="ci_e2b_api_key"
								type="password"
								placeholder="sk-e2b-..."
								bind:value={e2bApiKey}
								class="rounded-xl"
							/>
						</div>
						<div class="space-y-2">
							<Label for="ci_e2b_template">template</Label>
							<p class="text-xs text-zinc-500">e2b sandbox template name.</p>
							<Input
								id="ci_e2b_template"
								placeholder="code-interpreter-v1"
								bind:value={e2bTemplate}
								class="rounded-xl"
							/>
						</div>
					</div>
					<div class="space-y-2">
						<Label for="ci_e2b_packages">pre-installed packages</Label>
						<p class="text-xs text-zinc-500">
							comma-separated Python packages available in the sandbox.
						</p>
						<Input
							id="ci_e2b_packages"
							placeholder="numpy, pandas, matplotlib"
							bind:value={e2bAvailablePackages}
							class="rounded-xl"
						/>
					</div>
				</div>
			{/if}
		{/if}
	</CardContent>
</Card>
