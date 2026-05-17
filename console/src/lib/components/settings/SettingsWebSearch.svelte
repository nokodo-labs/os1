<script lang="ts">
	import type { Schemas } from '$lib/api'

	type Model = Schemas['Model']
	type Provider = Schemas['Provider']

	import ModelParamsEditor from '$lib/components/ModelParamsEditor.svelte'
	import SearchableModelPicker from '$lib/components/SearchableModelPicker.svelte'
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
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Switch } from '$lib/components/ui/switch'
	import { Textarea } from '$lib/components/ui/textarea'
	import { Bot, Lock, Pencil, Save, X } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type SearchAgent = 'native' | 'perplexity'
	type SearchEngine = 'perplexity' | 'searxng' | 'bing' | 'google'
	type WebLoaderEngine = 'native' | 'tavily' | 'playwright'
	type PerplexityModel =
		| 'sonar'
		| 'sonar-pro'
		| 'sonar-reasoning'
		| 'sonar-reasoning-pro'
		| 'sonar-deep-research'
	type SearchContextUsage = 'low' | 'medium' | 'high'
	type ModelType = 'chat_model' | 'embedding' | 'image' | 'audio' | 'video'

	function modelLabel(m: Model): string {
		const name = m.display_name || m.name || m.id
		const provider = providers.find((p) => p.id === m.provider_id)
		const providerName = provider?.name || m.provider_id
		return [name, providerName].filter(Boolean).join(' - ')
	}

	type Props = {
		maxChars?: string
		blacklistedDomains?: string
		agenticAgent?: SearchAgent
		agenticModelId?: string
		agenticSystemPrompt?: string
		agenticModelParams?: string
		agenticMaxIterations?: string
		engineEngine?: SearchEngine
		searxngInstanceUrl?: string
		searxngMaxResults?: string
		searxngMaxConcurrentRequests?: string
		searxngTimeoutSeconds?: string
		// web loaders
		webLoaderEngine?: WebLoaderEngine
		webLoaderTimeoutSeconds?: string
		webLoaderUserAgent?: string
		webLoaderMaxChars?: string
		tavilyExtractDepth?: 'basic' | 'advanced'
		tavilyApiKey?: string
		tavilyMaxConcurrentRequests?: string
		// perplexity
		perplexityApiKey?: string
		perplexityModel?: PerplexityModel
		perplexitySearchContextUsage?: SearchContextUsage
		perplexityTemperature?: string
		perplexityImageResultsEnabled?: boolean
		perplexityMaxConcurrentRequests?: string
		models?: Model[]
		providers?: Provider[]
		isFetchingModels?: boolean
		modelsError?: string | null
	}

	let {
		maxChars = $bindable(''),
		blacklistedDomains = $bindable(''),
		agenticAgent = $bindable<SearchAgent>('native'),
		agenticModelId = $bindable(''),
		agenticSystemPrompt = $bindable(''),
		agenticModelParams = $bindable('{}'),
		agenticMaxIterations = $bindable(''),
		engineEngine = $bindable<SearchEngine>('perplexity'),
		searxngInstanceUrl = $bindable(''),
		searxngMaxResults = $bindable(''),
		searxngMaxConcurrentRequests = $bindable(''),
		searxngTimeoutSeconds = $bindable(''),
		webLoaderEngine = $bindable<WebLoaderEngine>('native'),
		webLoaderTimeoutSeconds = $bindable(''),
		webLoaderUserAgent = $bindable(''),
		webLoaderMaxChars = $bindable(''),
		tavilyExtractDepth = $bindable<'basic' | 'advanced'>('advanced'),
		tavilyApiKey = $bindable(''),
		tavilyMaxConcurrentRequests = $bindable(''),
		perplexityApiKey = $bindable(''),
		perplexityModel = $bindable<PerplexityModel>('sonar'),
		perplexitySearchContextUsage = $bindable<SearchContextUsage>('medium'),
		perplexityTemperature = $bindable(''),
		perplexityImageResultsEnabled = $bindable(false),
		perplexityMaxConcurrentRequests = $bindable(''),
		models = [],
		providers = [],
		isFetchingModels = false,
		modelsError = null,
	}: Props = $props()

	const chatModels = $derived(models.filter((m) => m.model_type === 'chat_model'))
	let showNativeAgentModal = $state(false)
	let nativeAgentDraftModelId = $state('')
	let nativeAgentDraftSystemPrompt = $state('')
	let nativeAgentDraftModelParams = $state<Record<string, unknown>>({})
	let nativeAgentDraftMaxIterations = $state('')
	let nativeAgentError = $state<string | null>(null)

	let nativeAgentDraftModelType = $derived.by(() => {
		if (!nativeAgentDraftModelId) return null
		const model = models.find((m) => m.id === nativeAgentDraftModelId)
		return (model?.model_type ?? null) as ModelType | null
	})

	let nativeAgentSummary = $derived.by(() => {
		const model = getModelLabel(agenticModelId)
		const iterations = agenticMaxIterations || 'default'
		return `${model} · ${iterations} ${iterations === '1' ? 'iteration' : 'iterations'}`
	})

	function getModelLabel(modelId: string): string {
		if (!modelId) return 'task default'
		const model = models.find((m) => m.id === modelId)
		return model ? modelLabel(model) : modelId
	}

	function parseModelParams(value: string): Record<string, unknown> {
		try {
			const parsed: unknown = JSON.parse(value || '{}')
			if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
				return parsed as Record<string, unknown>
			}
		} catch {
			// handled by caller error state
		}
		throw new Error('model params must be a JSON object')
	}

	function openNativeAgentModal() {
		try {
			nativeAgentDraftModelParams = parseModelParams(agenticModelParams)
			nativeAgentDraftModelId = agenticModelId
			nativeAgentDraftSystemPrompt = agenticSystemPrompt
			nativeAgentDraftMaxIterations = agenticMaxIterations
			nativeAgentError = null
			showNativeAgentModal = true
		} catch (err: unknown) {
			nativeAgentError = err instanceof Error ? err.message : 'invalid native agent config'
			showNativeAgentModal = true
		}
	}

	function saveNativeAgentModal() {
		agenticModelId = nativeAgentDraftModelId
		agenticSystemPrompt = nativeAgentDraftSystemPrompt
		agenticModelParams = JSON.stringify(nativeAgentDraftModelParams, null, 2)
		agenticMaxIterations = nativeAgentDraftMaxIterations
		nativeAgentError = null
		showNativeAgentModal = false
	}
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>web search</CardTitle>
		<CardDescription>search engine, agentic search, and web loader settings.</CardDescription>
	</CardHeader>
	<CardContent class="space-y-5">
		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<Label for="ws_max_chars">web search max chars</Label>
				<p class="text-xs text-zinc-500">maximum characters returned by search tools.</p>
				<Input
					id="ws_max_chars"
					type="number"
					min="100"
					placeholder="50000"
					bind:value={maxChars}
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<Label for="ws_blacklisted_domains">blacklisted domains</Label>
				<p class="text-xs text-zinc-500">
					comma-separated domains to exclude from results.
				</p>
				<Input
					id="ws_blacklisted_domains"
					placeholder="twitter.com, reddit.com"
					bind:value={blacklistedDomains}
					class="rounded-xl"
				/>
			</div>
		</div>

		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<div class="mb-4 flex items-center justify-between">
				<div>
					<p class="text-sm font-medium">agentic web search</p>
					<p class="text-xs text-zinc-500">synthesis layer used by agentic_web_search.</p>
				</div>
				{#if isFetchingModels}
					<span class="text-xs text-zinc-500">loading...</span>
				{/if}
			</div>
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="ws_agentic_agent">agent</Label>
					<Select
						value={agenticAgent}
						onValueChange={(v: string) => (agenticAgent = v as SearchAgent)}
					>
						<SelectTrigger id="ws_agentic_agent" class="rounded-xl">
							<span class="truncate text-left">{agenticAgent}</span>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="native">native</SelectItem>
							<SelectItem value="perplexity">perplexity</SelectItem>
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label>native agent configuration</Label>
					<div
						class="flex items-center justify-between gap-3 rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3"
					>
						<div class="min-w-0">
							<p class="truncate text-sm text-zinc-200">{nativeAgentSummary}</p>
							<p class="text-xs text-zinc-500">
								model, prompt, and runtime parameters.
							</p>
						</div>
						<Button
							type="button"
							variant="outline"
							class="shrink-0 gap-2 rounded-xl"
							onclick={openNativeAgentModal}
						>
							<Pencil class="h-4 w-4" />
							configure
						</Button>
					</div>
				</div>
			</div>
			{#if modelsError}
				<p class="mt-3 text-xs text-red-300">{modelsError}</p>
			{/if}
		</div>

		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<p class="mb-4 text-sm font-medium">search engine</p>
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="ws_engine_engine">engine</Label>
					<Select
						value={engineEngine}
						onValueChange={(v: string) => (engineEngine = v as SearchEngine)}
					>
						<SelectTrigger id="ws_engine_engine" class="rounded-xl">
							<span class="truncate text-left">{engineEngine}</span>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="perplexity">perplexity</SelectItem>
							<SelectItem value="searxng">searxng</SelectItem>
							<SelectItem value="bing">bing</SelectItem>
							<SelectItem value="google">google</SelectItem>
						</SelectContent>
					</Select>
				</div>
			</div>
		</div>

		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<p class="mb-4 text-sm font-medium">searxng integration</p>
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="ws_searxng_url">instance url</Label>
					<Input
						id="ws_searxng_url"
						placeholder="http://searxng:8080"
						bind:value={searxngInstanceUrl}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="ws_searxng_max_results">max results</Label>
					<Input
						id="ws_searxng_max_results"
						type="number"
						min="1"
						placeholder="20"
						bind:value={searxngMaxResults}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="ws_searxng_concurrent">max concurrent requests</Label>
					<Input
						id="ws_searxng_concurrent"
						type="number"
						min="1"
						placeholder="5"
						bind:value={searxngMaxConcurrentRequests}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="ws_searxng_timeout">timeout (seconds)</Label>
					<Input
						id="ws_searxng_timeout"
						type="number"
						min="1"
						placeholder="10"
						bind:value={searxngTimeoutSeconds}
						class="rounded-xl"
					/>
				</div>
			</div>
		</div>

		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<p class="mb-4 text-sm font-medium">web loader</p>
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="ws_loader_engine">engine</Label>
					<Select
						value={webLoaderEngine}
						onValueChange={(v: string) => (webLoaderEngine = v as WebLoaderEngine)}
					>
						<SelectTrigger id="ws_loader_engine" class="rounded-xl">
							<span class="truncate text-left">{webLoaderEngine}</span>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="native">native</SelectItem>
							<SelectItem value="tavily">tavily</SelectItem>
							<SelectItem value="playwright">playwright</SelectItem>
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label for="ws_loader_timeout">timeout (seconds)</Label>
					<Input
						id="ws_loader_timeout"
						type="number"
						min="1"
						placeholder="10"
						bind:value={webLoaderTimeoutSeconds}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="ws_loader_max_chars">fetch max chars</Label>
					<Input
						id="ws_loader_max_chars"
						type="number"
						min="100"
						placeholder="50000"
						bind:value={webLoaderMaxChars}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2 md:col-span-2">
					<Label for="ws_loader_ua">user agent</Label>
					<Input
						id="ws_loader_ua"
						placeholder="Mozilla/5.0 (compatible; NokodoAI/1.0; +https://nokodo.ai)"
						bind:value={webLoaderUserAgent}
						class="rounded-xl font-mono text-xs"
					/>
				</div>
			</div>

			{#if webLoaderEngine === 'tavily'}
				<div class="mt-4 grid gap-4 md:grid-cols-2">
					<div class="space-y-2">
						<Label for="ws_tavily_depth">extract depth</Label>
						<Select
							value={tavilyExtractDepth}
							onValueChange={(v: string) =>
								(tavilyExtractDepth = v as 'basic' | 'advanced')}
						>
							<SelectTrigger id="ws_tavily_depth" class="rounded-xl">
								<span class="truncate text-left">{tavilyExtractDepth}</span>
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="basic">basic</SelectItem>
								<SelectItem value="advanced">advanced</SelectItem>
							</SelectContent>
						</Select>
					</div>
					<div class="space-y-2">
						<Label for="ws_tavily_concurrent">max concurrent requests</Label>
						<Input
							id="ws_tavily_concurrent"
							type="number"
							min="1"
							placeholder="10"
							bind:value={tavilyMaxConcurrentRequests}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<div class="flex items-center gap-2">
							<Label for="ws_tavily_api_key">tavily api key</Label>
							<span
								class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
							>
								<Lock class="h-3 w-3" />
								sensitive
							</span>
						</div>
						<Input
							id="ws_tavily_api_key"
							type="password"
							placeholder="tvly-..."
							bind:value={tavilyApiKey}
							class="rounded-xl"
						/>
					</div>
				</div>
			{/if}
		</div>

		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<p class="mb-4 text-sm font-medium">perplexity integration</p>
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<div class="flex items-center gap-2">
						<Label for="ws_px_api_key">api key</Label>
						<span
							class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
						>
							<Lock class="h-3 w-3" />
							sensitive
						</span>
					</div>
					<Input
						id="ws_px_api_key"
						type="password"
						placeholder="pplx-..."
						bind:value={perplexityApiKey}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="ws_px_model">model</Label>
					<Select
						value={perplexityModel}
						onValueChange={(v: string) => (perplexityModel = v as PerplexityModel)}
					>
						<SelectTrigger id="ws_px_model" class="rounded-xl">
							<span class="truncate text-left">{perplexityModel}</span>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="sonar">sonar</SelectItem>
							<SelectItem value="sonar-pro">sonar-pro</SelectItem>
							<SelectItem value="sonar-reasoning">sonar-reasoning</SelectItem>
							<SelectItem value="sonar-reasoning-pro">sonar-reasoning-pro</SelectItem>
							<SelectItem value="sonar-deep-research">sonar-deep-research</SelectItem>
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label for="ws_px_context">search context usage</Label>
					<Select
						value={perplexitySearchContextUsage}
						onValueChange={(v: string) =>
							(perplexitySearchContextUsage = v as SearchContextUsage)}
					>
						<SelectTrigger id="ws_px_context" class="rounded-xl">
							<span class="truncate text-left">{perplexitySearchContextUsage}</span>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="low">low</SelectItem>
							<SelectItem value="medium">medium</SelectItem>
							<SelectItem value="high">high</SelectItem>
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label for="ws_px_temperature">temperature</Label>
					<Input
						id="ws_px_temperature"
						type="number"
						step="0.05"
						min="0"
						max="2"
						placeholder="0.2"
						bind:value={perplexityTemperature}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="ws_px_concurrent">max concurrent requests</Label>
					<Input
						id="ws_px_concurrent"
						type="number"
						min="1"
						placeholder="10"
						bind:value={perplexityMaxConcurrentRequests}
						class="rounded-xl"
					/>
				</div>
				<div
					class="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3"
				>
					<div>
						<Label for="ws_px_images">image results</Label>
						<p class="text-xs text-zinc-500">
							allow tools to request image URLs when supported.
						</p>
					</div>
					<Switch
						id="ws_px_images"
						checked={perplexityImageResultsEnabled}
						onCheckedChange={(v: boolean) => (perplexityImageResultsEnabled = v)}
					/>
				</div>
			</div>
		</div>
	</CardContent>
</Card>

<Dialog.Root bind:open={showNativeAgentModal}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex h-[min(720px,calc(100vh-2rem))] w-[min(820px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div class="flex min-w-0 items-center gap-3">
					<div
						class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400"
					>
						<Bot class="h-4 w-4" />
					</div>
					<div class="min-w-0">
						<Dialog.Title class="text-lg font-semibold"
							>native web search agent</Dialog.Title
						>
						<p class="text-xs text-zinc-500">
							configure the agent used by native agentic web search.
						</p>
					</div>
				</div>
				<Button
					type="button"
					variant="ghost"
					size="icon"
					class="rounded-xl"
					onclick={() => (showNativeAgentModal = false)}
				>
					<X class="h-4 w-4" />
				</Button>
			</div>

			<div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-4">
				{#if nativeAgentError}
					<div class="rounded-lg bg-red-900/20 p-3 text-sm text-red-400">
						{nativeAgentError}
					</div>
				{/if}

				<div class="grid gap-4 md:grid-cols-[1fr_160px]">
					<div class="space-y-2">
						<Label for="ws_agent_modal_model">model</Label>
						<SearchableModelPicker
							items={chatModels.map((m) => ({
								value: m.id,
								label: m.display_name || m.name || m.id,
								sublabel: modelLabel(m).replace(
									`${m.display_name || m.name || m.id} - `,
									''
								),
							}))}
							value={nativeAgentDraftModelId}
							placeholder="task default"
							searchPlaceholder="search models..."
							allowClear={true}
							clearLabel="task default"
							emptyLabel="no models match your search"
							onChange={(v) => (nativeAgentDraftModelId = v)}
						/>
					</div>
					<div class="space-y-2">
						<Label for="ws_agent_modal_iterations">max iterations</Label>
						<Input
							id="ws_agent_modal_iterations"
							type="number"
							min="1"
							max="20"
							placeholder="4"
							bind:value={nativeAgentDraftMaxIterations}
							class="rounded-xl"
						/>
					</div>
				</div>

				<div class="space-y-2">
					<Label for="ws_agent_modal_prompt">system prompt</Label>
					<Textarea
						id="ws_agent_modal_prompt"
						bind:value={nativeAgentDraftSystemPrompt}
						class="min-h-44 rounded-xl font-mono text-xs"
					/>
				</div>

				{#if nativeAgentDraftModelType}
					<div class="border-t border-zinc-800 pt-4">
						<ModelParamsEditor
							modelType={nativeAgentDraftModelType}
							bind:params={nativeAgentDraftModelParams}
						/>
					</div>
				{:else}
					<p class="text-xs text-zinc-500">select a model to configure parameters.</p>
				{/if}
			</div>

			<div class="flex shrink-0 justify-end border-t border-zinc-800 px-6 py-4">
				<Button type="button" class="gap-2 rounded-xl" onclick={saveNativeAgentModal}>
					<Save class="h-4 w-4" />
					save agent config
				</Button>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
