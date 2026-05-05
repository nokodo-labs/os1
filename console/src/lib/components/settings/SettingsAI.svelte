<script lang="ts">
	import type { Schemas } from '$lib/api'

	type Agent = Schemas['Agent']
	type Model = Schemas['Model']
	type Provider = Schemas['Provider']

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
	import { ChevronDown, ChevronUp, X } from '@lucide/svelte'

	type ChatContextMode = 'recent' | 'relevant' | 'pinned'

	function agentLabel(a: Agent): string {
		return a.name || a.id
	}

	function modelLabel(m: Model): string {
		const name = m.display_name || m.name || m.id
		const provider = providers.find((p) => p.id === m.provider_id)
		const providerName = provider?.name || m.provider_id
		const adapterType = provider?.adapter_type
		const modelAdapter = m.adapter
		const adapterPart = adapterType
			? modelAdapter && modelAdapter !== adapterType
				? `${adapterType}/${modelAdapter}`
				: adapterType
			: (modelAdapter ?? null)
		return [name, providerName, adapterPart].filter(Boolean).join(' · ')
	}

	type Props = {
		// default agents
		defaultAgentIds?: string[]
		// memory
		memoryEnable?: boolean
		memorySimilarityThreshold?: string
		memoryTopK?: string
		memoryMessagesToConsider?: string
		// chat context
		chatContextEnabled?: boolean
		chatContextMode?: ChatContextMode
		chatContextTopK?: string
		chatContextSimilarityThreshold?: string
		// retrieval
		retrievalTurns?: string
		retrievalPreBuild?: boolean
		// tasks
		taskDefaultModelId?: string
		taskThreadMetadataModelId?: string
		taskThreadMaintenanceModelId?: string
		taskInputAutocompleteModelId?: string
		taskSummarizationModelId?: string
		taskMemoryPostProcessingModelId?: string
		taskWebSearchModelId?: string
		taskMaintenanceMaxCharsPerMessage?: string
		// media - images
		mediaImagesEnabled?: boolean
		mediaImagesModel?: string
		mediaImagesDefaultSize?: string
		mediaImagesDefaultSteps?: string
		mediaImagesDefaultN?: string
		mediaImagesMaxN?: string
		// media - videos
		mediaVideosEnabled?: boolean
		// media - audio
		mediaAudioEnabled?: boolean
		// attachments
		attachmentImageDecayTurns?: string
		attachmentAudioDecayTurns?: string
		attachmentVideoDecayTurns?: string
		attachmentRevealDecayTurns?: string
		// windowing
		windowingEnabled?: boolean
		windowingMaxMessages?: string
		windowingTriggerRatio?: string
		windowingHardRatio?: string
		windowingSummaryBatchSize?: string
		windowingMaxSummariesBeforeCondense?: string
		windowingToolResultMaxShare?: string
		windowingToolResultHardCap?: string
		windowingToolResultsCombinedMaxShare?: string
		windowingResponseHeadroom?: string
		windowingSummarizationMaxCharsPerMessage?: string
		// auxiliary (read-only)
		agents?: Agent[]
		models?: Model[]
		providers?: Provider[]
		isFetchingAgents?: boolean
		isFetchingModels?: boolean
		agentsError?: string | null
		modelsError?: string | null
	}

	let {
		defaultAgentIds = $bindable([]),
		memoryEnable = $bindable(false),
		memorySimilarityThreshold = $bindable(''),
		memoryTopK = $bindable(''),
		memoryMessagesToConsider = $bindable(''),
		chatContextEnabled = $bindable(true),
		chatContextMode = $bindable('recent'),
		chatContextTopK = $bindable(''),
		chatContextSimilarityThreshold = $bindable(''),
		retrievalTurns = $bindable(''),
		retrievalPreBuild = $bindable(true),
		taskDefaultModelId = $bindable(''),
		taskThreadMetadataModelId = $bindable(''),
		taskThreadMaintenanceModelId = $bindable(''),
		taskInputAutocompleteModelId = $bindable(''),
		taskSummarizationModelId = $bindable(''),
		taskMemoryPostProcessingModelId = $bindable(''),
		taskWebSearchModelId = $bindable(''),
		taskMaintenanceMaxCharsPerMessage = $bindable(''),
		mediaImagesEnabled = $bindable(true),
		mediaImagesModel = $bindable(''),
		mediaImagesDefaultSize = $bindable(''),
		mediaImagesDefaultSteps = $bindable(''),
		mediaImagesDefaultN = $bindable(''),
		mediaImagesMaxN = $bindable(''),
		mediaVideosEnabled = $bindable(false),
		mediaAudioEnabled = $bindable(false),
		attachmentImageDecayTurns = $bindable(''),
		attachmentAudioDecayTurns = $bindable(''),
		attachmentVideoDecayTurns = $bindable(''),
		attachmentRevealDecayTurns = $bindable(''),
		windowingEnabled = $bindable(true),
		windowingMaxMessages = $bindable(''),
		windowingTriggerRatio = $bindable(''),
		windowingHardRatio = $bindable(''),
		windowingSummaryBatchSize = $bindable(''),
		windowingMaxSummariesBeforeCondense = $bindable(''),
		windowingToolResultMaxShare = $bindable(''),
		windowingToolResultHardCap = $bindable(''),
		windowingToolResultsCombinedMaxShare = $bindable(''),
		windowingResponseHeadroom = $bindable(''),
		windowingSummarizationMaxCharsPerMessage = $bindable(''),
		agents = [],
		models = [],
		providers = [],
		isFetchingAgents = false,
		isFetchingModels = false,
		agentsError = null,
		modelsError = null,
	}: Props = $props()

	const availableAgentsToAdd = $derived(agents.filter((a) => !defaultAgentIds.includes(a.id)))

	const chatModels = $derived(models.filter((m) => m.model_type === 'chat_model'))
	const imageModels = $derived(models.filter((m) => m.model_type === 'image'))

	function getModelLabel(modelId: string): string {
		if (!modelId) return 'none'
		const m = models.find((x) => x.id === modelId)
		return m ? modelLabel(m) : modelId
	}
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>AI</CardTitle>
		<CardDescription>agent defaults and behavior.</CardDescription>
	</CardHeader>
	<CardContent class="space-y-6">
		<!-- default agents -->
		<div class="space-y-2">
			<div class="flex items-center justify-between gap-2">
				<div>
					<Label for="default_agents">default agents</Label>
					<p class="text-xs text-zinc-500">
						tried in order; first available agent is used.
					</p>
				</div>
				{#if isFetchingAgents}
					<span class="text-xs text-zinc-500">loading…</span>
				{/if}
			</div>
			{#if defaultAgentIds.length > 0}
				<ul class="space-y-1">
					{#each defaultAgentIds as agentId, idx (agentId)}
						{@const label = agents.find((x) => x.id === agentId)}
						<li
							class="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
						>
							<span class="w-5 shrink-0 font-mono text-xs text-zinc-500"
								>{idx + 1}.</span
							>
							<span class="flex-1 truncate"
								>{label ? agentLabel(label) : agentId}</span
							>
							<button
								class="text-zinc-500 hover:text-zinc-300 disabled:opacity-30"
								disabled={idx === 0}
								onclick={() => {
									const copy = [...defaultAgentIds]
									;[copy[idx - 1], copy[idx]] = [copy[idx], copy[idx - 1]]
									defaultAgentIds = copy
								}}
								title="move up"
							>
								<ChevronUp class="h-4 w-4" />
							</button>
							<button
								class="text-zinc-500 hover:text-zinc-300 disabled:opacity-30"
								disabled={idx === defaultAgentIds.length - 1}
								onclick={() => {
									const copy = [...defaultAgentIds]
									;[copy[idx], copy[idx + 1]] = [copy[idx + 1], copy[idx]]
									defaultAgentIds = copy
								}}
								title="move down"
							>
								<ChevronDown class="h-4 w-4" />
							</button>
							<button
								class="text-zinc-500 hover:text-red-400"
								onclick={() => {
									defaultAgentIds = defaultAgentIds.filter((_, i) => i !== idx)
								}}
								title="remove"
							>
								<X class="h-4 w-4" />
							</button>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="text-xs text-zinc-500 italic">no default agents configured</p>
			{/if}
			{#if availableAgentsToAdd.length > 0}
				<Select
					value=""
					onValueChange={(v: string) => {
						if (v) defaultAgentIds = [...defaultAgentIds, v]
					}}
				>
					<SelectTrigger id="default_agents" class="rounded-xl">
						<span class="text-zinc-500">add agent…</span>
					</SelectTrigger>
					<SelectContent>
						{#each availableAgentsToAdd as a (a.id)}
							<SelectItem value={a.id}>{agentLabel(a)}</SelectItem>
						{/each}
					</SelectContent>
				</Select>
			{/if}
			{#if agentsError}
				<p class="text-xs text-red-300">{agentsError}</p>
			{/if}
		</div>

		<!-- memory -->
		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<div class="mb-4 flex items-center justify-between">
				<div>
					<p class="text-sm font-medium">memory</p>
					<p class="text-xs text-zinc-500">retrieval and consolidation settings.</p>
				</div>
				<Switch
					id="ai_memory_enable"
					checked={memoryEnable}
					onCheckedChange={(v: boolean) => (memoryEnable = v)}
				/>
			</div>
			{#if memoryEnable}
				<div class="grid gap-4 md:grid-cols-2">
					<div class="space-y-2">
						<Label for="ai_similarity">similarity threshold</Label>
						<p class="text-xs text-zinc-500">
							minimum cosine similarity for a memory to be retrieved (0 = any, 1 =
							exact).
						</p>
						<Input
							id="ai_similarity"
							type="number"
							step="0.01"
							min="0"
							max="1"
							bind:value={memorySimilarityThreshold}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="ai_top_k">top k</Label>
						<p class="text-xs text-zinc-500">
							max memories retrieved per conversation turn.
						</p>
						<Input
							id="ai_top_k"
							type="number"
							min="1"
							bind:value={memoryTopK}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="ai_messages">messages to consider</Label>
						<p class="text-xs text-zinc-500">
							recent messages scanned when retrieving or consolidating memories.
						</p>
						<Input
							id="ai_messages"
							type="number"
							min="1"
							bind:value={memoryMessagesToConsider}
							class="rounded-xl"
						/>
					</div>
				</div>
			{/if}
		</div>

		<!-- chat context -->
		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<div class="mb-4 flex items-center justify-between">
				<div>
					<p class="text-sm font-medium">chat context</p>
					<p class="text-xs text-zinc-500">how prior chats are added to context.</p>
				</div>
				<Switch bind:checked={chatContextEnabled} />
			</div>
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="ai_chat_mode">mode</Label>
					<p class="text-xs text-zinc-500">
						determines which past chats are included in the agent's context window.
					</p>
					<Select
						value={chatContextMode}
						onValueChange={(v: string) => (chatContextMode = v as ChatContextMode)}
					>
						<SelectTrigger id="ai_chat_mode" class="rounded-xl">
							<span class="truncate text-left">{chatContextMode}</span>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="recent">recent</SelectItem>
							<SelectItem value="relevant">relevant</SelectItem>
							<SelectItem value="pinned">pinned</SelectItem>
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label for="ai_chat_top_k">top k</Label>
					<p class="text-xs text-zinc-500">
						number of past chats to include in context per turn.
					</p>
					<Input
						id="ai_chat_top_k"
						type="number"
						min="1"
						bind:value={chatContextTopK}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="ai_chat_threshold">similarity threshold</Label>
					<p class="text-xs text-zinc-500">
						minimum score for vector results (0.0–1.0). lower = more results.
					</p>
					<Input
						id="ai_chat_threshold"
						type="number"
						min="0"
						max="1"
						step="0.05"
						bind:value={chatContextSimilarityThreshold}
						class="rounded-xl"
					/>
				</div>
			</div>
		</div>

		<!-- retrieval -->
		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<p class="mb-4 text-sm font-medium">retrieval</p>
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="retrieval_turns">retrieval turns</Label>
					<p class="text-xs text-zinc-500">
						recent turns to use when building memory and chat context queries.
					</p>
					<Input
						id="retrieval_turns"
						type="number"
						min="1"
						bind:value={retrievalTurns}
						placeholder="3"
						class="rounded-xl"
					/>
				</div>
				<div
					class="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3"
				>
					<div>
						<p class="text-sm font-medium">pre-build retrieval query</p>
						<p class="text-xs text-zinc-500">
							embed the retrieval query once before filters run.
						</p>
					</div>
					<Switch bind:checked={retrievalPreBuild} />
				</div>
			</div>
		</div>

		<!-- task models -->
		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<div class="mb-4 flex items-center justify-between">
				<div>
					<p class="text-sm font-medium">task models</p>
					<p class="text-xs text-zinc-500">overrides for background task runs.</p>
				</div>
				{#if isFetchingModels}
					<span class="text-xs text-zinc-500">loading…</span>
				{/if}
			</div>
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="task_default_model">default model</Label>
					<p class="text-xs text-zinc-500">
						fallback model used when no task-specific model is set.
					</p>
					<Select
						value={taskDefaultModelId}
						onValueChange={(v: string) => (taskDefaultModelId = v)}
					>
						<SelectTrigger id="task_default_model" class="rounded-xl">
							<span class="truncate text-left"
								>{getModelLabel(taskDefaultModelId)}</span
							>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="">none</SelectItem>
							{#each chatModels as model (model.id)}
								<SelectItem value={model.id}>{modelLabel(model)}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label for="task_thread_metadata_model">thread metadata model</Label>
					<p class="text-xs text-zinc-500">
						model used to generate thread titles and tags automatically.
					</p>
					<Select
						value={taskThreadMetadataModelId}
						onValueChange={(v: string) => (taskThreadMetadataModelId = v)}
					>
						<SelectTrigger id="task_thread_metadata_model" class="rounded-xl">
							<span class="truncate text-left"
								>{getModelLabel(taskThreadMetadataModelId)}</span
							>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="">none</SelectItem>
							{#each chatModels as model (model.id)}
								<SelectItem value={model.id}>{modelLabel(model)}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label for="task_thread_maintenance_model">thread maintenance model</Label>
					<p class="text-xs text-zinc-500">
						model used for inactive-thread summaries and metadata maintenance.
					</p>
					<Select
						value={taskThreadMaintenanceModelId}
						onValueChange={(v: string) => (taskThreadMaintenanceModelId = v)}
					>
						<SelectTrigger id="task_thread_maintenance_model" class="rounded-xl">
							<span class="truncate text-left"
								>{getModelLabel(taskThreadMaintenanceModelId)}</span
							>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="">none</SelectItem>
							{#each chatModels as model (model.id)}
								<SelectItem value={model.id}>{modelLabel(model)}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label for="task_input_autocomplete_model">input autocomplete model</Label>
					<p class="text-xs text-zinc-500">
						model used to suggest completions as the user types.
					</p>
					<Select
						value={taskInputAutocompleteModelId}
						onValueChange={(v: string) => (taskInputAutocompleteModelId = v)}
					>
						<SelectTrigger id="task_input_autocomplete_model" class="rounded-xl">
							<span class="truncate text-left"
								>{getModelLabel(taskInputAutocompleteModelId)}</span
							>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="">none</SelectItem>
							{#each chatModels as model (model.id)}
								<SelectItem value={model.id}>{modelLabel(model)}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label for="task_summarization_model">summarization model</Label>
					<p class="text-xs text-zinc-500">
						model used for thread context summarization.
					</p>
					<Select
						value={taskSummarizationModelId}
						onValueChange={(v: string) => (taskSummarizationModelId = v)}
					>
						<SelectTrigger id="task_summarization_model" class="rounded-xl">
							<span class="truncate text-left"
								>{getModelLabel(taskSummarizationModelId)}</span
							>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="">none</SelectItem>
							{#each chatModels as model (model.id)}
								<SelectItem value={model.id}>{modelLabel(model)}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label for="task_memory_pp_model">memory post-processing model</Label>
					<p class="text-xs text-zinc-500">
						model used for memory deduplication, updates, and deletions.
					</p>
					<Select
						value={taskMemoryPostProcessingModelId}
						onValueChange={(v: string) => (taskMemoryPostProcessingModelId = v)}
					>
						<SelectTrigger id="task_memory_pp_model" class="rounded-xl">
							<span class="truncate text-left"
								>{getModelLabel(taskMemoryPostProcessingModelId)}</span
							>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="">none</SelectItem>
							{#each chatModels as model (model.id)}
								<SelectItem value={model.id}>{modelLabel(model)}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label for="task_web_search_model">web search model</Label>
					<p class="text-xs text-zinc-500">model used for native agentic web search.</p>
					<Select
						value={taskWebSearchModelId}
						onValueChange={(v: string) => (taskWebSearchModelId = v)}
					>
						<SelectTrigger id="task_web_search_model" class="rounded-xl">
							<span class="truncate text-left"
								>{getModelLabel(taskWebSearchModelId)}</span
							>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="">none</SelectItem>
							{#each chatModels as model (model.id)}
								<SelectItem value={model.id}>{modelLabel(model)}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label for="task_maintenance_max_chars">maintenance transcript max chars</Label>
					<p class="text-xs text-zinc-500">
						max characters per message in maintenance transcripts. leave empty for
						unlimited.
					</p>
					<Input
						id="task_maintenance_max_chars"
						type="number"
						min="1"
						placeholder="unlimited"
						bind:value={taskMaintenanceMaxCharsPerMessage}
						class="rounded-xl"
					/>
				</div>
			</div>
			{#if modelsError}
				<p class="mt-3 text-xs text-red-300">{modelsError}</p>
			{/if}
		</div>

		<!-- attachments -->
		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<p class="mb-1 text-sm font-medium">attachment decay</p>
			<p class="mb-4 text-xs text-zinc-500">
				turns after the last interaction before an active attachment auto-decays to
				reference state.
			</p>
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="attach_image_decay">image decay turns</Label>
					<Input
						id="attach_image_decay"
						type="number"
						min="1"
						bind:value={attachmentImageDecayTurns}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="attach_audio_decay">audio decay turns</Label>
					<Input
						id="attach_audio_decay"
						type="number"
						min="1"
						bind:value={attachmentAudioDecayTurns}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="attach_video_decay">video decay turns</Label>
					<Input
						id="attach_video_decay"
						type="number"
						min="1"
						bind:value={attachmentVideoDecayTurns}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="attach_reveal_decay">reveal decay turns</Label>
					<p class="text-xs text-zinc-500">
						turns before a manually revealed attachment decays again.
					</p>
					<Input
						id="attach_reveal_decay"
						type="number"
						min="1"
						bind:value={attachmentRevealDecayTurns}
						class="rounded-xl"
					/>
				</div>
			</div>
		</div>

		<!-- windowing -->
		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<div class="mb-4 flex items-center justify-between">
				<div>
					<p class="text-sm font-medium">context windowing</p>
					<p class="text-xs text-zinc-500">
						token-aware summarization and truncation to keep threads within model
						limits.
					</p>
				</div>
				<Switch
					id="windowing_enabled"
					checked={windowingEnabled}
					onCheckedChange={(v: boolean) => (windowingEnabled = v)}
				/>
			</div>
			{#if windowingEnabled}
				<div class="grid gap-4 md:grid-cols-2">
					<div class="space-y-2">
						<Label for="win_max_messages">max messages</Label>
						<p class="text-xs text-zinc-500">
							cap unsummarized messages regardless of token budget.
						</p>
						<Input
							id="win_max_messages"
							type="number"
							min="1"
							bind:value={windowingMaxMessages}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="win_trigger_ratio">trigger ratio</Label>
						<p class="text-xs text-zinc-500">
							fraction of token budget that triggers background summarization
							(0.1–0.95).
						</p>
						<Input
							id="win_trigger_ratio"
							type="number"
							step="0.01"
							min="0.1"
							max="0.95"
							bind:value={windowingTriggerRatio}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="win_hard_ratio">hard truncation ratio</Label>
						<p class="text-xs text-zinc-500">
							fraction that triggers hard truncation as a last resort (0.5–1.0).
						</p>
						<Input
							id="win_hard_ratio"
							type="number"
							step="0.01"
							min="0.5"
							max="1.0"
							bind:value={windowingHardRatio}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="win_summary_batch">summary batch size</Label>
						<p class="text-xs text-zinc-500">oldest messages summarized per batch.</p>
						<Input
							id="win_summary_batch"
							type="number"
							min="1"
							bind:value={windowingSummaryBatchSize}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="win_max_summaries">max summaries before condense</Label>
						<p class="text-xs text-zinc-500">
							condense accumulated summaries when this count is reached.
						</p>
						<Input
							id="win_max_summaries"
							type="number"
							min="2"
							bind:value={windowingMaxSummariesBeforeCondense}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="win_response_headroom">response headroom (tokens)</Label>
						<p class="text-xs text-zinc-500">tokens reserved for the model's reply.</p>
						<Input
							id="win_response_headroom"
							type="number"
							min="256"
							bind:value={windowingResponseHeadroom}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="win_tool_max_share">tool result max share</Label>
						<p class="text-xs text-zinc-500">
							max fraction of budget a single tool result may use (0.05–0.75).
						</p>
						<Input
							id="win_tool_max_share"
							type="number"
							step="0.01"
							min="0.05"
							max="0.75"
							bind:value={windowingToolResultMaxShare}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="win_tool_hard_cap">tool result hard cap (chars)</Label>
						<p class="text-xs text-zinc-500">
							absolute character ceiling per tool result.
						</p>
						<Input
							id="win_tool_hard_cap"
							type="number"
							min="1000"
							bind:value={windowingToolResultHardCap}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="win_tools_combined_share">tool results combined max share</Label
						>
						<p class="text-xs text-zinc-500">
							max fraction of budget for all tool results combined (0.10–0.95).
						</p>
						<Input
							id="win_tools_combined_share"
							type="number"
							step="0.01"
							min="0.10"
							max="0.95"
							bind:value={windowingToolResultsCombinedMaxShare}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="win_summarization_max_chars"
							>summarization transcript max chars</Label
						>
						<p class="text-xs text-zinc-500">
							max characters per message in summarization transcripts. leave empty for
							unlimited.
						</p>
						<Input
							id="win_summarization_max_chars"
							type="number"
							min="1"
							placeholder="unlimited"
							bind:value={windowingSummarizationMaxCharsPerMessage}
							class="rounded-xl"
						/>
					</div>
				</div>
			{/if}
		</div>

		<!-- media generation -->
		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<p class="mb-4 text-sm font-medium">media generation</p>

			<!-- images -->
			<div class="mb-4 space-y-3">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm">image generation</p>
						<p class="text-xs text-zinc-500">
							enable AI image generation capabilities.
						</p>
					</div>
					<Switch
						id="ai_media_images_enabled"
						checked={mediaImagesEnabled}
						onCheckedChange={(v: boolean) => (mediaImagesEnabled = v)}
					/>
				</div>
				{#if mediaImagesEnabled}
					<div class="grid gap-4 md:grid-cols-2">
						<div class="space-y-2">
							<Label for="ai_img_model">image model</Label>
							<p class="text-xs text-zinc-500">model used for image generation.</p>
							<Select
								value={mediaImagesModel}
								onValueChange={(v: string) => (mediaImagesModel = v)}
							>
								<SelectTrigger id="ai_img_model" class="rounded-xl">
									<span class="truncate text-left">
										{getModelLabel(mediaImagesModel)}
									</span>
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="">none</SelectItem>
									{#each imageModels as model (model.id)}
										<SelectItem value={model.id}>{modelLabel(model)}</SelectItem
										>
									{/each}
								</SelectContent>
							</Select>
						</div>
						<div class="space-y-2">
							<Label for="ai_img_size">default size</Label>
							<p class="text-xs text-zinc-500">WIDTHxHEIGHT format.</p>
							<Input
								id="ai_img_size"
								placeholder="1024x1024"
								bind:value={mediaImagesDefaultSize}
								class="rounded-xl"
							/>
						</div>
						<div class="space-y-2">
							<Label for="ai_img_steps">default steps</Label>
							<p class="text-xs text-zinc-500">generation steps (if supported).</p>
							<Input
								id="ai_img_steps"
								type="number"
								min="1"
								bind:value={mediaImagesDefaultSteps}
								class="rounded-xl"
							/>
						</div>
						<div class="space-y-2">
							<Label for="ai_img_default_n">default n</Label>
							<p class="text-xs text-zinc-500">default images per prompt (1–10).</p>
							<Input
								id="ai_img_default_n"
								type="number"
								min="1"
								max="10"
								bind:value={mediaImagesDefaultN}
								class="rounded-xl"
							/>
						</div>
						<div class="space-y-2">
							<Label for="ai_img_max_n">max n</Label>
							<p class="text-xs text-zinc-500">max images per request (1–10).</p>
							<Input
								id="ai_img_max_n"
								type="number"
								min="1"
								max="10"
								bind:value={mediaImagesMaxN}
								class="rounded-xl"
							/>
						</div>
					</div>
				{/if}
			</div>

			<!-- videos -->
			<div class="mb-4 flex items-center justify-between">
				<div>
					<p class="text-sm">video generation</p>
					<p class="text-xs text-zinc-500">enable AI video generation (scaffold).</p>
				</div>
				<Switch
					id="ai_media_videos_enabled"
					checked={mediaVideosEnabled}
					onCheckedChange={(v: boolean) => (mediaVideosEnabled = v)}
				/>
			</div>

			<!-- audio -->
			<div class="flex items-center justify-between">
				<div>
					<p class="text-sm">audio generation</p>
					<p class="text-xs text-zinc-500">enable AI audio generation (scaffold).</p>
				</div>
				<Switch
					id="ai_media_audio_enabled"
					checked={mediaAudioEnabled}
					onCheckedChange={(v: boolean) => (mediaAudioEnabled = v)}
				/>
			</div>
		</div>
	</CardContent>
</Card>
