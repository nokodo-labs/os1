<script lang="ts">
	import {
		AgentsService,
		ModelsService,
		ThreadsService,
		type Agent,
		type Message,
		type MessageCreate,
		type Model,
		type Thread,
		type ThreadCreate,
	} from '$lib/api'
	import { auth } from '$lib/auth.svelte'
	import AclModal from '$lib/components/AclModal.svelte'
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
	import { onMount } from 'svelte'

	let agents = $state<Agent[]>([])
	let models = $state<Model[]>([])

	let isFetching = $state(true)
	let error = $state<string | null>(null)

	let thread = $state<Thread | null>(null)
	let messages = $state<Message[]>([])
	let isWorking = $state(false)
	let actionError = $state<string | null>(null)
	let isAclOpen = $state(false)

	let threadTitle = $state('')
	let messageContent = $state('')
	let selectedAgentId = $state<string>('')
	let selectedModelId = $state<string>('')

	async function loadMeta() {
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
			console.error('Failed to load playground metadata', e)
			error = 'Failed to load models/agents'
		} finally {
			isFetching = false
		}
	}

	onMount(() => {
		loadMeta()
	})

	function getAgentLabel(agentId: string) {
		const a = agents.find((a) => a.id === agentId)
		return a ? a.name : agentId
	}

	function getModelLabel(modelId: string) {
		const m = models.find((m) => m.id === modelId)
		return m ? m.display_name || m.name : modelId
	}

	async function refreshMessages() {
		if (!thread) return
		messages = await ThreadsService.listMessagesThreadsThreadIdMessagesGet(thread.id)
	}

	async function createThread() {
		actionError = null
		if (!auth.user) {
			actionError = 'You must be logged in to create a thread.'
			return
		}

		isWorking = true
		try {
			const payload: ThreadCreate = {
				owner_id: auth.user.id,
				title: threadTitle.trim() ? threadTitle.trim() : null,
			}
			thread = await ThreadsService.createThreadThreadsPost(payload)
			messages = []
			await refreshMessages()
		} catch (e: any) {
			console.error('Failed to create thread', e)
			actionError = e?.message || 'Failed to create thread'
		} finally {
			isWorking = false
		}
	}

	async function sendMessage() {
		actionError = null
		if (!thread) {
			actionError = 'Create a thread first.'
			return
		}
		if (!auth.user) {
			actionError = 'You must be logged in to send a message.'
			return
		}
		if (!messageContent.trim()) return

		isWorking = true
		try {
			const metadata: Record<string, any> = {}
			if (selectedModelId) metadata.model_id = selectedModelId
			if (selectedAgentId) metadata.agent_id = selectedAgentId

			const payload: MessageCreate = {
				content: messageContent.trim(),
				sender_user_id: auth.user.id,
				sender_agent_id: selectedAgentId || null,
				metadata_: Object.keys(metadata).length ? metadata : undefined,
			}

			await ThreadsService.createMessageThreadsThreadIdMessagesPost(thread.id, payload)
			messageContent = ''
			await refreshMessages()
		} catch (e: any) {
			console.error('Failed to send message', e)
			actionError = e?.message || 'Failed to send message'
		} finally {
			isWorking = false
		}
	}

	function resetSession() {
		thread = null
		messages = []
		threadTitle = ''
		messageContent = ''
		selectedAgentId = ''
		selectedModelId = ''
		actionError = null
		isAclOpen = false
	}
</script>

<div class="space-y-6">
	<div>
		<h2 class="text-2xl font-bold tracking-tight">playground</h2>
		<p class="text-zinc-400">test agents and models by creating threads + messages.</p>
	</div>

	{#if isFetching}
		<div class="flex h-64 items-center justify-center">
			<NokodoLoader />
		</div>
	{:else if error}
		<div
			class="rounded-2xl border border-red-900/50 bg-red-900/10 p-6 text-center text-red-400"
		>
			<p>{error}</p>
			<Button variant="outline" class="mt-4" onclick={loadMeta}>Retry</Button>
		</div>
	{:else}
		<div class="grid gap-6 lg:grid-cols-2">
			<Card class="rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
				<CardHeader>
					<CardTitle>session</CardTitle>
					<CardDescription>create a thread and post messages.</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4">
					{#if actionError}
						<div class="rounded-lg bg-red-900/20 p-3 text-sm text-red-400">
							{actionError}
						</div>
					{/if}

					<div class="space-y-2">
						<Label for="threadTitle">thread title (optional)</Label>
						<Input
							id="threadTitle"
							bind:value={threadTitle}
							class="rounded-xl"
							placeholder="e.g. model sanity check"
						/>
					</div>

					<div class="flex gap-2">
						<Button class="rounded-xl" onclick={createThread} disabled={isWorking}>
							{thread ? 'new thread' : 'create thread'}
						</Button>
						<Button
							variant="outline"
							class="rounded-xl"
							onclick={resetSession}
							disabled={isWorking}
						>
							reset
						</Button>
					</div>

					{#if thread}
						<div
							class="rounded-xl border border-zinc-800 bg-zinc-950/50 p-3 text-sm text-zinc-400"
						>
							<div class="flex justify-between">
								<span>thread id:</span>
								<span class="font-mono text-xs">{thread.id}</span>
							</div>
							<div class="mt-3 flex justify-end">
								<Button variant="outline" class="rounded-xl" onclick={() => (isAclOpen = true)}>
									permissions
								</Button>
							</div>
						</div>
					{/if}

					<div class="space-y-2">
						<Label>model (optional)</Label>
						<Select
							value={selectedModelId}
							onValueChange={(v: string) => (selectedModelId = v)}
						>
							<SelectTrigger class="rounded-xl">
								<span class="truncate text-left">
									{selectedModelId ? getModelLabel(selectedModelId) : 'none'}
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
						<Label>agent (optional)</Label>
						<Select
							value={selectedAgentId}
							onValueChange={(v: string) => (selectedAgentId = v)}
						>
							<SelectTrigger class="rounded-xl">
								<span class="truncate text-left">
									{selectedAgentId ? getAgentLabel(selectedAgentId) : 'none'}
								</span>
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="">none</SelectItem>
								{#each agents as agent}
									<SelectItem value={agent.id}>{agent.name}</SelectItem>
								{/each}
							</SelectContent>
						</Select>
					</div>

					<div class="space-y-2">
						<Label for="message">message</Label>
						<textarea
							id="message"
							bind:value={messageContent}
							rows={6}
							placeholder="type a message to store on the thread..."
							class="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
						></textarea>
					</div>
				</CardContent>
				<CardFooter class="flex justify-end">
					<Button
						class="rounded-xl"
						onclick={sendMessage}
						disabled={isWorking || !thread || !messageContent.trim()}
					>
						{isWorking ? 'sending...' : 'send message'}
					</Button>
				</CardFooter>
			</Card>

			<Card class="rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
				<CardHeader>
					<CardTitle>messages</CardTitle>
					<CardDescription>stored messages for the current thread.</CardDescription>
				</CardHeader>
				<CardContent class="space-y-3">
					{#if !thread}
						<div
							class="rounded-lg border border-dashed border-zinc-800 p-12 text-center text-zinc-500"
						>
							create a thread to start.
						</div>
					{:else if messages.length === 0}
						<div
							class="rounded-lg border border-dashed border-zinc-800 p-12 text-center text-zinc-500"
						>
							no messages yet.
						</div>
					{:else}
						{#each messages as msg}
							<div class="rounded-xl border border-zinc-800 bg-zinc-950/50 p-3">
								<div
									class="mb-2 flex items-center justify-between text-xs text-zinc-500"
								>
									<span class="font-mono">{msg.id}</span>
									<span>{msg.created_at}</span>
								</div>
								<p class="text-sm whitespace-pre-wrap text-zinc-200">
									{msg.content}
								</p>
							</div>
						{/each}
					{/if}
				</CardContent>
				<CardFooter class="flex justify-end">
					<Button
						variant="outline"
						class="rounded-xl"
						onclick={refreshMessages}
						disabled={!thread || isWorking}
					>
						reload
					</Button>
				</CardFooter>
			</Card>
		</div>
	{/if}
</div>

{#if thread}
	<AclModal bind:open={isAclOpen} resourceType="thread" resourceId={thread.id} title="thread permissions" />
{/if}
