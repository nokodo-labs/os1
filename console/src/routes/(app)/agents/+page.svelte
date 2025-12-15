<script lang="ts">
	import {
		AgentsService,
		ModelsService,
		type Agent,
		type AgentCreate,
		type AgentVisibility,
		type Model,
	} from '$lib/api'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardFooter,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Pencil, Plus } from '@lucide/svelte'
	import { onMount } from 'svelte'

	let agents = $state<Agent[]>([])
	let models = $state<Model[]>([])
	let showModal = $state(false)
	let isFetching = $state(true)
	let isLoading = $state(false)
	let error = $state<string | null>(null)
	let submitError = $state<string | null>(null)

	let formName = $state('')
	let formDescription = $state('')
	let formSystemPrompt = $state('')
	let formVisibility = $state<AgentVisibility>('admin-only')
	let formModelId = $state<string>('')

	async function fetchData() {
		isFetching = true
		error = null
		try {
			const [agentsData, modelsData] = await Promise.all([
				AgentsService.listAgentsAgentsGet(),
				ModelsService.listModelsModelsGet(),
			])
			agents = agentsData
			models = modelsData
		} catch (e) {
			console.error('Failed to load agents/models', e)
			error = 'Failed to load agents'
		} finally {
			isFetching = false
		}
	}

	onMount(() => {
		fetchData()
	})

	function openCreateModal() {
		formName = ''
		formDescription = ''
		formSystemPrompt = ''
		formVisibility = 'admin-only'
		formModelId = ''
		submitError = null
		showModal = true
	}

	function getModelLabel(modelId: string | null | undefined) {
		if (!modelId) return 'none'
		const m = models.find((m) => m.id === modelId)
		return m ? m.display_name || m.name : modelId
	}

	async function handleSubmit(e: Event) {
		e.preventDefault()
		isLoading = true
		submitError = null

		try {
			const payload: AgentCreate = {
				name: formName.trim(),
				description: formDescription.trim() ? formDescription.trim() : null,
				system_prompt: formSystemPrompt.trim() ? formSystemPrompt.trim() : null,
				visibility: formVisibility,
				model_id: formModelId ? formModelId : null,
			}

			await AgentsService.createAgentAgentsPost(payload)
			showModal = false
			await fetchData()
		} catch (e: any) {
			console.error('Failed to create agent', e)
			submitError = e?.message || 'Failed to create agent'
		} finally {
			isLoading = false
		}
	}
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">agents</h2>
			<p class="text-zinc-400">create and manage agents.</p>
		</div>
		<Button onclick={openCreateModal} class="gap-2 rounded-xl">
			<Plus class="h-4 w-4" />
			add agent
		</Button>
	</div>

	{#if isFetching}
		<div class="flex flex-col items-center justify-center gap-4 py-16">
			<NokodoLoader expanded={true} />
		</div>
	{:else if error}
		<div
			class="rounded-2xl border border-red-900/50 bg-red-900/10 p-6 text-center text-red-400"
		>
			<p>{error}</p>
			<Button variant="outline" class="mt-4" onclick={fetchData}>Retry</Button>
		</div>
	{:else}
		<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
			{#each agents as agent}
				<Card class="overflow-hidden rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
					<CardHeader>
						<div class="flex items-start justify-between">
							<div>
								<CardTitle>{agent.name}</CardTitle>
								<CardDescription>{agent.visibility || 'admin-only'}</CardDescription
								>
							</div>
							<Button
								variant="ghost"
								size="icon"
								class="h-8 w-8 text-zinc-500"
								disabled
								title="editing not implemented yet"
							>
								<Pencil class="h-4 w-4" />
							</Button>
						</div>
					</CardHeader>
					<CardContent>
						<div class="space-y-1 text-sm text-zinc-400">
							<div class="flex justify-between">
								<span>model:</span>
								<span class="truncate">{getModelLabel(agent.model_id)}</span>
							</div>
							{#if agent.description}
								<div class="mt-2 border-t border-zinc-800 pt-2">
									<p class="text-xs text-zinc-500">{agent.description}</p>
								</div>
							{/if}
						</div>
					</CardContent>
				</Card>
			{/each}

			{#if agents.length === 0}
				<EmptyState message="no agents yet." hint="create an agent to get started." />
			{/if}
		</div>
	{/if}
</div>

{#if showModal}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
		<Card class="w-full max-w-lg rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
			<CardHeader>
				<CardTitle>create agent</CardTitle>
				<CardDescription>define prompting + attach a model (optional).</CardDescription>
			</CardHeader>
			<form onsubmit={handleSubmit}>
				<CardContent class="max-h-[60vh] space-y-4 overflow-y-auto pr-2">
					{#if submitError}
						<div class="rounded-lg bg-red-900/20 p-3 text-sm text-red-400">
							{submitError}
						</div>
					{/if}

					<div class="space-y-2">
						<Label for="name">name</Label>
						<Input
							id="name"
							bind:value={formName}
							required
							placeholder="e.g. nokodo coder"
							class="rounded-xl"
						/>
					</div>

					<div class="space-y-2">
						<Label for="model">model (optional)</Label>
						<Select
							value={formModelId}
							onValueChange={(v: string) => (formModelId = v)}
						>
							<SelectTrigger class="rounded-xl">
								<span class="truncate text-left">
									{formModelId ? getModelLabel(formModelId) : 'none'}
								</span>
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="">none</SelectItem>
								{#each models as model}
									<SelectItem value={model.id}
										>{model.display_name || model.name}</SelectItem
									>
								{/each}
							</SelectContent>
						</Select>
					</div>

					<div class="space-y-2">
						<Label for="visibility">visibility</Label>
						<select
							id="visibility"
							bind:value={formVisibility}
							class="flex h-10 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
						>
							<option value="admin-only">admin-only</option>
							<option value="private">private</option>
							<option value="public">public</option>
						</select>
					</div>

					<div class="space-y-2">
						<Label for="description">description (optional)</Label>
						<textarea
							id="description"
							bind:value={formDescription}
							rows={3}
							placeholder="what does this agent do?"
							class="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
						></textarea>
					</div>

					<div class="space-y-2">
						<Label for="system_prompt">system prompt (optional)</Label>
						<textarea
							id="system_prompt"
							bind:value={formSystemPrompt}
							rows={6}
							placeholder="you are ..."
							class="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-sm"
						></textarea>
					</div>
				</CardContent>
				<CardFooter class="flex justify-end gap-2">
					<Button
						type="button"
						variant="outline"
						class="rounded-xl"
						disabled={isLoading}
						onclick={() => (showModal = false)}
					>
						cancel
					</Button>
					<Button
						type="submit"
						class="rounded-xl"
						disabled={isLoading || !formName.trim()}
					>
						{isLoading ? 'creating...' : 'create'}
					</Button>
				</CardFooter>
			</form>
		</Card>
	</div>
{/if}
