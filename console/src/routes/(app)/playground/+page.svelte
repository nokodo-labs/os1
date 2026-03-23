<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'

	type Agent = Schemas['Agent']
	type Message = Schemas['Message']
	type MessageCreate = Schemas['MessageCreate']
	type Model = Schemas['Model']
	type Thread = Schemas['Thread']
	type ThreadCreate = Schemas['ThreadCreate']

	import { auth } from '$lib/auth.svelte'
	import AclModal from '$lib/components/AclModal.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { fade, slide } from 'svelte/transition'
	import {
		BrainCircuit,
		Bot,
		Cpu,
		Hammer,
		MessageSquarePlus,
		Play,
		RefreshCw,
		SendHorizonal,
		Settings,
		ShieldCheck,
		Sparkles,
		Terminal,
		Hash,
	} from '@lucide/svelte'
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
				api.GET('/v1/agents').then((r) => unwrap(r)),
				api.GET('/v1/models').then((r) => unwrap(r)),
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
		messages = unwrap(
			await api.GET('/v1/threads/{thread_id}/messages', {
				params: { path: { thread_id: thread.id } },
			})
		)
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
				is_archived: false,
				is_temporary: true,
			}
			thread = unwrap(await api.POST('/v1/threads', { body: payload }))
			messages = []
			await refreshMessages()
		} catch (e: unknown) {
			console.error('Failed to create thread', e)
			actionError = e instanceof Error ? e.message : String(e)
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
			const metadata: Record<string, unknown> = {}
			if (selectedModelId) metadata.model_id = selectedModelId
			if (selectedAgentId) metadata.agent_id = selectedAgentId

			const payload: MessageCreate = {
				type: 'user',
				content: messageContent.trim(),
				sender_user_id: auth.user.id,
				sender_agent_id: selectedAgentId || null,
				metadata_:
					Object.keys(metadata).length > 0
						? (metadata as unknown as MessageCreate['metadata_'])
						: undefined,
			}

			unwrap(
				await api.POST('/v1/threads/{thread_id}/messages', {
					params: { path: { thread_id: thread.id } },
					body: payload,
				})
			)
			messageContent = ''
			await refreshMessages()
		} catch (e: unknown) {
			console.error('Failed to send message', e)
			actionError = e instanceof Error ? e.message : String(e)
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

<div class="flex min-h-0 flex-1 flex-col gap-6">
	<div class="flex shrink-0 items-center justify-between">
		<div>
			<h2 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
				<Hammer class="h-6 w-6 text-emerald-400" />
				playground
			</h2>
			<p class="text-zinc-400">test agents and models directly via api.</p>
		</div>
		{#if thread}
			<Button
				variant="outline"
				class="rounded-xl border-zinc-800 bg-zinc-900/50 text-zinc-300 hover:bg-zinc-800 hover:text-white"
				onclick={resetSession}
				disabled={isWorking}
			>
				<RefreshCw class="mr-1.5 h-4 w-4 {isWorking ? 'animate-spin' : ''}" />
				reset session
			</Button>
		{/if}
	</div>

	{#if isFetching}
		<div class="flex min-h-0 flex-1 items-center justify-center">
			<NokodoLoader />
		</div>
	{:else if error}
		<div class="rounded-2xl border border-red-900/50 bg-red-900/10 p-6 text-center text-red-400 shadow-xl shadow-red-900/5">
			<p>{error}</p>
			<Button variant="outline" class="mt-4 border-red-800 hover:bg-red-900" onclick={loadMeta}>
				<RefreshCw class="mr-2 h-4 w-4" /> retry
			</Button>
		</div>
	{:else}
		<div class="grid min-h-0 flex-1 gap-6 lg:grid-cols-[400px_minmax(0,1fr)]">
			<!-- sidebar config pane -->
			<div class="flex flex-col gap-6 overflow-y-auto pr-2" transition:fade>
				{#if !thread}
					<div class="flex flex-col gap-5 rounded-3xl border border-zinc-800/60 bg-zinc-900/40 p-6 shadow-2xl backdrop-blur-xl">
						<div>
							<h3 class="flex items-center gap-2 text-lg font-semibold text-zinc-100">
								<Settings class="h-5 w-5 text-zinc-400" />
								configuration
							</h3>
							<p class="text-sm text-zinc-500">setup the environment before initializing.</p>
						</div>

						{#if actionError}
							<div class="rounded-lg bg-red-900/20 p-3 text-sm text-red-400">
								{actionError}
							</div>
						{/if}

						<div class="space-y-4">
							<div class="space-y-2">
								<Label class="text-xs font-medium text-zinc-400">agent configuration</Label>
								<Select value={selectedAgentId} onValueChange={(v: string) => (selectedAgentId = v)}>
									<SelectTrigger class="h-11 rounded-xl border-zinc-800 bg-zinc-950/50">
										<div class="flex items-center gap-2 truncate text-left">
											<Bot class="h-4 w-4 text-emerald-400" />
											{selectedAgentId ? getAgentLabel(selectedAgentId) : 'none (default behavior)'}
										</div>
									</SelectTrigger>
									<SelectContent>
										<SelectItem value="">none (default behavior)</SelectItem>
										{#each agents as agent (agent.id)}
											<SelectItem value={agent.id}>{agent.name}</SelectItem>
										{/each}
									</SelectContent>
								</Select>
							</div>

							<div class="space-y-2">
								<Label class="text-xs font-medium text-zinc-400">model override</Label>
								<Select value={selectedModelId} onValueChange={(v: string) => (selectedModelId = v)}>
									<SelectTrigger class="h-11 rounded-xl border-zinc-800 bg-zinc-950/50">
										<div class="flex items-center gap-2 truncate text-left">
											<Cpu class="h-4 w-4 text-indigo-400" />
											{selectedModelId ? getModelLabel(selectedModelId) : 'use agent default'}
										</div>
									</SelectTrigger>
									<SelectContent>
										<SelectItem value="">use agent default</SelectItem>
										{#each models as model (model.id)}
											<SelectItem value={model.id}>{model.display_name || model.name}</SelectItem>
										{/each}
									</SelectContent>
								</Select>
							</div>

							<div class="space-y-2 pt-2">
								<Label for="threadTitle" class="text-xs font-medium text-zinc-400">session title (optional)</Label>
								<Input
									id="threadTitle"
									bind:value={threadTitle}
									class="h-11 rounded-xl border-zinc-800 bg-zinc-950/50 focus:border-emerald-500/50 focus:ring-emerald-500/20"
									placeholder="e.g. reasoning test run..."
								/>
							</div>
						</div>

						<Button
							class="group relative mt-2 h-12 w-full overflow-hidden rounded-xl bg-linear-to-r from-emerald-500 to-teal-500 text-white shadow-lg transition-all hover:scale-[1.02] hover:shadow-emerald-500/25"
							onclick={createThread}
							disabled={isWorking}
						>
							<div class="absolute inset-0 bg-white/20 opacity-0 transition-opacity group-hover:opacity-100"></div>
							<div class="relative flex items-center justify-center gap-2">
								{#if isWorking}
									<RefreshCw class="h-5 w-5 animate-spin" />
									<span class="font-medium">initializing...</span>
								{:else}
									<Play class="h-5 w-5 fill-current" />
									<span class="font-medium">start session</span>
								{/if}
							</div>
						</Button>
					</div>
				{:else}
					<!-- active session controls pane -->
					<div class="flex flex-col gap-4 rounded-3xl border border-emerald-900/30 bg-linear-to-br from-emerald-950/20 to-zinc-900/40 p-6 shadow-2xl backdrop-blur-xl" transition:slide>
						<div class="flex items-start justify-between">
							<div class="space-y-1">
								<h3 class="flex items-center gap-2 text-lg font-semibold text-emerald-400">
									<Sparkles class="h-5 w-5" />
									session active
								</h3>
								<div class="flex items-center gap-1.5 text-xs text-zinc-500">
									<Hash class="h-3.5 w-3.5" />
									<span class="font-mono">{thread.id}</span>
								</div>
							</div>
							<Button
								variant="outline"
								size="sm"
								class="h-8 rounded-lg border-zinc-800 bg-zinc-950/50 text-xs hover:bg-zinc-800"
								onclick={() => (isAclOpen = true)}
							>
								<ShieldCheck class="mr-1.5 h-3.5 w-3.5" /> permissions
							</Button>
						</div>

						<div class="mt-4 flex flex-col gap-3 rounded-2xl bg-zinc-950/50 p-4">
							{#if actionError}
								<div class="rounded-lg bg-red-900/20 p-2 text-sm text-red-400 mb-1">
									{actionError}
								</div>
							{/if}
							<Label for="message" class="text-xs font-semibold tracking-wider text-zinc-400 uppercase">Input Payload</Label>
							<textarea
								id="message"
								bind:value={messageContent}
								rows={6}
								placeholder="enter prompt text..."
								class="w-full resize-none rounded-xl border-0 bg-transparent py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:ring-0"
								style="box-shadow: none;"
							></textarea>
							<div class="flex justify-end pt-2 border-t border-zinc-800/50">
								<Button
									class="group relative h-10 overflow-hidden rounded-xl bg-linear-to-r from-zinc-200 to-zinc-400 text-zinc-950 shadow-md transition-all hover:scale-[1.02] hover:shadow-white/10"
									onclick={sendMessage}
									disabled={isWorking || !messageContent.trim()}
								>
									<div class="relative flex items-center gap-2 px-2">
										{#if isWorking}
											<RefreshCw class="h-4 w-4 animate-spin" />
											<span class="font-medium">executing...</span>
										{:else}
											<span class="font-medium">send message</span>
											<SendHorizonal class="h-4 w-4 transition-transform group-hover:translate-x-1 group-hover:-translate-y-1" />
										{/if}
									</div>
								</Button>
							</div>
						</div>
					</div>
				{/if}
			</div>

			<!-- main chat pane -->
			<div class="flex min-h-0 flex-col rounded-3xl border border-zinc-800/60 bg-zinc-950/50 shadow-2xl">
				<div class="flex shrink-0 items-center justify-between border-b border-zinc-800/50 px-6 py-4 backdrop-blur-md">
					<div class="flex items-center gap-3">
						<Terminal class="h-5 w-5 text-zinc-400" />
						<div class="text-sm font-medium text-zinc-200">execution log</div>
					</div>
					{#if thread}
						<Button
							variant="ghost"
							size="sm"
							class="h-8 rounded-xl text-zinc-400 hover:text-white"
							onclick={refreshMessages}
							disabled={isWorking}
						>
							<RefreshCw class="mr-1.5 h-3.5 w-3.5 {isWorking ? 'animate-spin' : ''}" /> reload log
						</Button>
					{/if}
				</div>

				<div class="min-h-0 flex-1 space-y-6 overflow-y-auto p-6 scroll-smooth">
					{#if !thread}
						<div class="flex h-full flex-col items-center justify-center text-center opacity-40" transition:fade>
							<MessageSquarePlus class="mb-4 h-16 w-16 text-zinc-600" />
							<p class="text-lg font-medium text-zinc-400">ready to start</p>
							<p class="mt-1 max-w-sm text-sm text-zinc-500">configure an agent and click start session to begin testing.</p>
						</div>
					{:else if messages.length === 0}
						<div class="flex h-full flex-col items-center justify-center text-center opacity-40" transition:fade>
							<BrainCircuit class="mb-4 h-16 w-16 text-zinc-600" />
							<p class="text-lg font-medium text-zinc-400">thread created</p>
							<p class="mt-1 text-sm text-zinc-500">awaiting your input...</p>
						</div>
					{:else}
						{#each messages as msg (msg.id)}
							{@const isUser = msg.type === 'user'}
							<div class="flex w-full {isUser ? 'justify-end' : 'justify-start'}" transition:slide={{ duration: 200 }}>
								<div class="max-w-[85%] sm:max-w-[75%]">
									<div class="mb-1.5 flex items-center {isUser ? 'justify-end' : 'justify-start'} gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
										{#if isUser}
											<span class="opacity-60">{new Date(msg.created_at).toLocaleTimeString()}</span>
											<span>user payload</span>
										{:else}
											<span class="text-emerald-500">agent response</span>
											<span class="opacity-60">{new Date(msg.created_at).toLocaleTimeString()}</span>
										{/if}
									</div>
									<div class="relative overflow-hidden rounded-2xl p-4 {isUser ? 'bg-zinc-800 text-zinc-100' : 'border border-zinc-800 bg-zinc-900/80 text-zinc-200'}">
										<p class="whitespace-pre-wrap text-sm leading-relaxed">{msg.content}</p>
									</div>
									<div class="mt-1.5 flex {isUser ? 'justify-end' : 'justify-start'}">
										<span class="font-mono text-[10px] text-zinc-600">{msg.id}</span>
									</div>
								</div>
							</div>
						{/each}
						<!-- dummy anchor to auto-scroll to bottom could be placed here -->
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>

{#if thread}
	<AclModal
		bind:open={isAclOpen}
		resourceType="thread"
		resourceId={thread.id}
		title="thread permissions"
	/>
{/if}
