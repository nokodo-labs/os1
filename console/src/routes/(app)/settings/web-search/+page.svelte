<script lang="ts">
	import { api } from '$lib/api'
	import SettingsWebSearch from '$lib/components/settings/SettingsWebSearch.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { parseCommaList, parseJsonObject, toStringOrEmpty } from '$lib/settings/utils'
	import { asNumberOrUndefined } from '$lib/utils/settingsNumbers'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'

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

	const ctx = getSettingsContext()

	let maxChars = $state('')
	let blacklistedDomains = $state('')
	let agenticAgent = $state<SearchAgent>('native')
	let agenticModelId = $state('')
	let agenticSystemPrompt = $state('')
	let agenticModelParams = $state('{}')
	let agenticMaxIterations = $state('')
	let engineEngine = $state<SearchEngine>('perplexity')
	let webLoaderEngine = $state<WebLoaderEngine>('native')
	let webLoaderTimeoutSeconds = $state('')
	let webLoaderUserAgent = $state('')
	let webLoaderMaxChars = $state('')
	let tavilyExtractDepth = $state<'basic' | 'advanced'>('advanced')
	let tavilyApiKey = $state('')
	let tavilyMaxConcurrentRequests = $state('')
	let searxngInstanceUrl = $state('')
	let searxngMaxResults = $state('')
	let searxngMaxConcurrentRequests = $state('')
	let searxngTimeoutSeconds = $state('')
	let perplexityApiKey = $state('')
	let perplexityModel = $state<PerplexityModel>('sonar')
	let perplexitySearchContextUsage = $state<SearchContextUsage>('medium')
	let perplexityTemperature = $state('')
	let perplexityImageResultsEnabled = $state(false)
	let perplexityMaxConcurrentRequests = $state('')

	type Original = {
		maxChars: string
		blacklistedDomains: string
		agenticAgent: SearchAgent
		agenticModelId: string
		agenticSystemPrompt: string
		agenticModelParams: string
		agenticMaxIterations: string
		engineEngine: SearchEngine
		webLoaderEngine: WebLoaderEngine
		webLoaderTimeoutSeconds: string
		webLoaderUserAgent: string
		webLoaderMaxChars: string
		tavilyExtractDepth: 'basic' | 'advanced'
		tavilyApiKey: string
		tavilyMaxConcurrentRequests: string
		searxngInstanceUrl: string
		searxngMaxResults: string
		searxngMaxConcurrentRequests: string
		searxngTimeoutSeconds: string
		perplexityApiKey: string
		perplexityModel: PerplexityModel
		perplexitySearchContextUsage: SearchContextUsage
		perplexityTemperature: string
		perplexityImageResultsEnabled: boolean
		perplexityMaxConcurrentRequests: string
	}
	let original = $state<Original | null>(null)

	function formatJsonObject(value: unknown): string {
		if (value === null || typeof value !== 'object' || Array.isArray(value)) return '{}'
		return JSON.stringify(value, null, 2)
	}

	$effect(() => {
		const r = ctx.response
		if (!r) return
		const ws = r.data.web_search
		maxChars = toStringOrEmpty(ws?.max_chars)
		blacklistedDomains = (ws?.blacklisted_domains ?? []).join(', ')
		const agentic = ws?.agentic
		agenticAgent = (agentic?.agent ?? 'native') as SearchAgent
		agenticModelId = agentic?.model_id ?? ''
		agenticSystemPrompt = agentic?.system_prompt ?? ''
		agenticModelParams = formatJsonObject(agentic?.model_params)
		agenticMaxIterations = toStringOrEmpty(agentic?.max_iterations)
		engineEngine = (ws?.search_engines?.engine ?? 'perplexity') as SearchEngine
		const wl = ws?.web_loaders
		webLoaderEngine = (wl?.engine ?? 'native') as WebLoaderEngine
		webLoaderTimeoutSeconds = toStringOrEmpty(wl?.timeout_seconds)
		webLoaderUserAgent = toStringOrEmpty(wl?.user_agent)
		webLoaderMaxChars = toStringOrEmpty(wl?.max_chars)
		const tavily = wl?.tavily
		tavilyExtractDepth = (tavily?.extract_depth ?? 'advanced') as 'basic' | 'advanced'
		tavilyApiKey = tavily?.api_key ?? ''
		tavilyMaxConcurrentRequests = toStringOrEmpty(tavily?.max_concurrent_requests)
		const integrations = r.data.integrations
		const searxng = integrations?.searxng
		searxngInstanceUrl = toStringOrEmpty(searxng?.instance_url)
		searxngMaxResults = toStringOrEmpty(searxng?.max_results)
		searxngMaxConcurrentRequests = toStringOrEmpty(searxng?.max_concurrent_requests)
		searxngTimeoutSeconds = toStringOrEmpty(searxng?.timeout_seconds)
		const perplexity = integrations?.perplexity
		perplexityApiKey = perplexity?.api_key ?? ''
		perplexityModel = (perplexity?.model ?? 'sonar') as PerplexityModel
		perplexitySearchContextUsage = (perplexity?.search_context_usage ??
			'medium') as SearchContextUsage
		perplexityTemperature = toStringOrEmpty(perplexity?.temperature)
		perplexityImageResultsEnabled = perplexity?.image_results_enabled ?? false
		perplexityMaxConcurrentRequests = toStringOrEmpty(perplexity?.max_concurrent_requests)

		original = {
			maxChars,
			blacklistedDomains,
			agenticAgent,
			agenticModelId,
			agenticSystemPrompt,
			agenticModelParams,
			agenticMaxIterations,
			engineEngine,
			webLoaderEngine,
			webLoaderTimeoutSeconds,
			webLoaderUserAgent,
			webLoaderMaxChars,
			tavilyExtractDepth,
			tavilyApiKey,
			tavilyMaxConcurrentRequests,
			searxngInstanceUrl,
			searxngMaxResults,
			searxngMaxConcurrentRequests,
			searxngTimeoutSeconds,
			perplexityApiKey,
			perplexityModel,
			perplexitySearchContextUsage,
			perplexityTemperature,
			perplexityImageResultsEnabled,
			perplexityMaxConcurrentRequests,
		}
	})

	const hasChanges = $derived(
		original !== null &&
			(maxChars !== original.maxChars ||
				blacklistedDomains !== original.blacklistedDomains ||
				agenticAgent !== original.agenticAgent ||
				agenticModelId !== original.agenticModelId ||
				agenticSystemPrompt !== original.agenticSystemPrompt ||
				agenticModelParams !== original.agenticModelParams ||
				agenticMaxIterations !== original.agenticMaxIterations ||
				engineEngine !== original.engineEngine ||
				webLoaderEngine !== original.webLoaderEngine ||
				webLoaderTimeoutSeconds !== original.webLoaderTimeoutSeconds ||
				webLoaderUserAgent !== original.webLoaderUserAgent ||
				webLoaderMaxChars !== original.webLoaderMaxChars ||
				tavilyExtractDepth !== original.tavilyExtractDepth ||
				tavilyApiKey !== original.tavilyApiKey ||
				tavilyMaxConcurrentRequests !== original.tavilyMaxConcurrentRequests ||
				searxngInstanceUrl !== original.searxngInstanceUrl ||
				searxngMaxResults !== original.searxngMaxResults ||
				searxngMaxConcurrentRequests !== original.searxngMaxConcurrentRequests ||
				searxngTimeoutSeconds !== original.searxngTimeoutSeconds ||
				perplexityApiKey !== original.perplexityApiKey ||
				perplexityModel !== original.perplexityModel ||
				perplexitySearchContextUsage !== original.perplexitySearchContextUsage ||
				perplexityTemperature !== original.perplexityTemperature ||
				perplexityImageResultsEnabled !== original.perplexityImageResultsEnabled ||
				perplexityMaxConcurrentRequests !== original.perplexityMaxConcurrentRequests)
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	function resetDraft() {
		if (!original) return
		maxChars = original.maxChars
		blacklistedDomains = original.blacklistedDomains
		agenticAgent = original.agenticAgent
		agenticModelId = original.agenticModelId
		agenticSystemPrompt = original.agenticSystemPrompt
		agenticModelParams = original.agenticModelParams
		agenticMaxIterations = original.agenticMaxIterations
		engineEngine = original.engineEngine
		webLoaderEngine = original.webLoaderEngine
		webLoaderTimeoutSeconds = original.webLoaderTimeoutSeconds
		webLoaderUserAgent = original.webLoaderUserAgent
		webLoaderMaxChars = original.webLoaderMaxChars
		tavilyExtractDepth = original.tavilyExtractDepth
		tavilyApiKey = original.tavilyApiKey
		tavilyMaxConcurrentRequests = original.tavilyMaxConcurrentRequests
		searxngInstanceUrl = original.searxngInstanceUrl
		searxngMaxResults = original.searxngMaxResults
		searxngMaxConcurrentRequests = original.searxngMaxConcurrentRequests
		searxngTimeoutSeconds = original.searxngTimeoutSeconds
		perplexityApiKey = original.perplexityApiKey
		perplexityModel = original.perplexityModel
		perplexitySearchContextUsage = original.perplexitySearchContextUsage
		perplexityTemperature = original.perplexityTemperature
		perplexityImageResultsEnabled = original.perplexityImageResultsEnabled
		perplexityMaxConcurrentRequests = original.perplexityMaxConcurrentRequests
		saveError = null
		saveSuccess = null
	}

	async function save() {
		if (!ctx.response || !hasChanges || !original) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const data: Record<string, unknown> = {}

			if (
				maxChars !== original.maxChars ||
				blacklistedDomains !== original.blacklistedDomains ||
				agenticAgent !== original.agenticAgent ||
				agenticModelId !== original.agenticModelId ||
				agenticSystemPrompt !== original.agenticSystemPrompt ||
				agenticModelParams !== original.agenticModelParams ||
				agenticMaxIterations !== original.agenticMaxIterations ||
				engineEngine !== original.engineEngine ||
				webLoaderEngine !== original.webLoaderEngine ||
				webLoaderTimeoutSeconds !== original.webLoaderTimeoutSeconds ||
				webLoaderUserAgent !== original.webLoaderUserAgent ||
				webLoaderMaxChars !== original.webLoaderMaxChars ||
				tavilyExtractDepth !== original.tavilyExtractDepth ||
				tavilyApiKey !== original.tavilyApiKey ||
				tavilyMaxConcurrentRequests !== original.tavilyMaxConcurrentRequests
			) {
				const wsPatch: Record<string, unknown> = {}
				if (maxChars !== original.maxChars)
					wsPatch.max_chars = asNumberOrUndefined(maxChars)
				if (blacklistedDomains !== original.blacklistedDomains)
					wsPatch.blacklisted_domains = parseCommaList(blacklistedDomains)

				if (
					agenticAgent !== original.agenticAgent ||
					agenticModelId !== original.agenticModelId ||
					agenticSystemPrompt !== original.agenticSystemPrompt ||
					agenticModelParams !== original.agenticModelParams ||
					agenticMaxIterations !== original.agenticMaxIterations
				) {
					const ap: Record<string, unknown> = {}
					if (agenticAgent !== original.agenticAgent) ap.agent = agenticAgent
					if (agenticModelId !== original.agenticModelId)
						ap.model_id = agenticModelId || null
					if (agenticSystemPrompt !== original.agenticSystemPrompt)
						ap.system_prompt = agenticSystemPrompt
					if (agenticModelParams !== original.agenticModelParams)
						ap.model_params = parseJsonObject(agenticModelParams)
					if (agenticMaxIterations !== original.agenticMaxIterations)
						ap.max_iterations = asNumberOrUndefined(agenticMaxIterations)
					wsPatch.agentic = ap
				}

				if (engineEngine !== original.engineEngine) {
					wsPatch.search_engines = { engine: engineEngine }
				}

				if (
					webLoaderEngine !== original.webLoaderEngine ||
					webLoaderTimeoutSeconds !== original.webLoaderTimeoutSeconds ||
					webLoaderUserAgent !== original.webLoaderUserAgent ||
					webLoaderMaxChars !== original.webLoaderMaxChars ||
					tavilyExtractDepth !== original.tavilyExtractDepth ||
					tavilyApiKey !== original.tavilyApiKey ||
					tavilyMaxConcurrentRequests !== original.tavilyMaxConcurrentRequests
				) {
					const wlp: Record<string, unknown> = {}
					if (webLoaderEngine !== original.webLoaderEngine) wlp.engine = webLoaderEngine
					if (webLoaderTimeoutSeconds !== original.webLoaderTimeoutSeconds)
						wlp.timeout_seconds = asNumberOrUndefined(webLoaderTimeoutSeconds)
					if (webLoaderUserAgent !== original.webLoaderUserAgent)
						wlp.user_agent = webLoaderUserAgent || undefined
					if (webLoaderMaxChars !== original.webLoaderMaxChars)
						wlp.max_chars = asNumberOrUndefined(webLoaderMaxChars)
					if (
						tavilyExtractDepth !== original.tavilyExtractDepth ||
						tavilyApiKey !== original.tavilyApiKey ||
						tavilyMaxConcurrentRequests !== original.tavilyMaxConcurrentRequests
					) {
						const tp: Record<string, unknown> = {}
						if (tavilyApiKey !== original.tavilyApiKey)
							tp.api_key = tavilyApiKey || null
						if (tavilyExtractDepth !== original.tavilyExtractDepth)
							tp.extract_depth = tavilyExtractDepth
						if (tavilyMaxConcurrentRequests !== original.tavilyMaxConcurrentRequests)
							tp.max_concurrent_requests = asNumberOrUndefined(
								tavilyMaxConcurrentRequests
							)
						wlp.tavily = tp
					}
					wsPatch.web_loaders = wlp
				}

				data.web_search = wsPatch
			}

			if (
				searxngInstanceUrl !== original.searxngInstanceUrl ||
				searxngMaxResults !== original.searxngMaxResults ||
				searxngMaxConcurrentRequests !== original.searxngMaxConcurrentRequests ||
				searxngTimeoutSeconds !== original.searxngTimeoutSeconds ||
				perplexityApiKey !== original.perplexityApiKey ||
				perplexityModel !== original.perplexityModel ||
				perplexitySearchContextUsage !== original.perplexitySearchContextUsage ||
				perplexityTemperature !== original.perplexityTemperature ||
				perplexityImageResultsEnabled !== original.perplexityImageResultsEnabled ||
				perplexityMaxConcurrentRequests !== original.perplexityMaxConcurrentRequests
			) {
				const intPatch: Record<string, unknown> = {}
				if (
					searxngInstanceUrl !== original.searxngInstanceUrl ||
					searxngMaxResults !== original.searxngMaxResults ||
					searxngMaxConcurrentRequests !== original.searxngMaxConcurrentRequests ||
					searxngTimeoutSeconds !== original.searxngTimeoutSeconds
				) {
					const sp: Record<string, unknown> = {}
					if (searxngInstanceUrl !== original.searxngInstanceUrl)
						sp.instance_url = searxngInstanceUrl || undefined
					if (searxngMaxResults !== original.searxngMaxResults)
						sp.max_results = asNumberOrUndefined(searxngMaxResults)
					if (searxngMaxConcurrentRequests !== original.searxngMaxConcurrentRequests)
						sp.max_concurrent_requests = asNumberOrUndefined(
							searxngMaxConcurrentRequests
						)
					if (searxngTimeoutSeconds !== original.searxngTimeoutSeconds)
						sp.timeout_seconds = asNumberOrUndefined(searxngTimeoutSeconds)
					intPatch.searxng = sp
				}
				if (
					perplexityApiKey !== original.perplexityApiKey ||
					perplexityModel !== original.perplexityModel ||
					perplexitySearchContextUsage !== original.perplexitySearchContextUsage ||
					perplexityTemperature !== original.perplexityTemperature ||
					perplexityImageResultsEnabled !== original.perplexityImageResultsEnabled ||
					perplexityMaxConcurrentRequests !== original.perplexityMaxConcurrentRequests
				) {
					const pp: Record<string, unknown> = {}
					if (perplexityApiKey !== original.perplexityApiKey)
						pp.api_key = perplexityApiKey || null
					if (perplexityModel !== original.perplexityModel)
						pp.model = perplexityModel || undefined
					if (perplexitySearchContextUsage !== original.perplexitySearchContextUsage)
						pp.search_context_usage = perplexitySearchContextUsage || undefined
					if (perplexityTemperature !== original.perplexityTemperature)
						pp.temperature = asNumberOrUndefined(perplexityTemperature)
					if (perplexityImageResultsEnabled !== original.perplexityImageResultsEnabled)
						pp.image_results_enabled = perplexityImageResultsEnabled
					if (
						perplexityMaxConcurrentRequests !== original.perplexityMaxConcurrentRequests
					)
						pp.max_concurrent_requests = asNumberOrUndefined(
							perplexityMaxConcurrentRequests
						)
					intPatch.perplexity = pp
				}
				data.integrations = intPatch
			}

			const result = await api.PATCH('/v1/settings', {
				body: { data, expected_versions: ctx.response.versions ?? null },
			})
			if (result.error) {
				if (result.response.status === 409) {
					saveError = 'settings were updated elsewhere. reload and try again.'
				} else {
					const detail = result.error?.detail
					saveError = typeof detail === 'string' ? detail : 'failed to save settings'
				}
				return
			}
			ctx.setFromResponse(result.data!)
			saveSuccess = 'saved'
		} catch (e) {
			console.error('Failed to save web search settings', e)
			saveError = 'failed to save settings'
		} finally {
			isSaving = false
		}
	}
</script>

<div class="flex flex-col gap-4">
	<div class="flex items-center justify-between gap-2">
		<div>
			{#if saveError}
				<p class="text-sm text-red-400">{saveError}</p>
			{:else if saveSuccess}
				<p class="text-sm text-emerald-400">{saveSuccess}</p>
			{/if}
		</div>
		<div class="flex items-center gap-2">
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={ctx.fetchSettings}
				disabled={ctx.isFetching || isSaving}
			>
				<RefreshCw class="mr-1.5 h-4 w-4" />
				reload
			</Button>
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={resetDraft}
				disabled={!hasChanges || isSaving}
			>
				<RotateCcw class="mr-1.5 h-4 w-4" />
				reset
			</Button>
			<Button class="rounded-xl" onclick={save} disabled={!hasChanges || isSaving}>
				<Save class="mr-1.5 h-4 w-4" />
				{isSaving ? 'saving...' : 'save'}
			</Button>
		</div>
	</div>

	<SettingsWebSearch
		bind:maxChars
		bind:blacklistedDomains
		bind:agenticAgent
		bind:agenticModelId
		bind:agenticSystemPrompt
		bind:agenticModelParams
		bind:agenticMaxIterations
		bind:engineEngine
		bind:searxngInstanceUrl
		bind:searxngMaxResults
		bind:searxngMaxConcurrentRequests
		bind:searxngTimeoutSeconds
		bind:webLoaderEngine
		bind:webLoaderTimeoutSeconds
		bind:webLoaderUserAgent
		bind:webLoaderMaxChars
		bind:tavilyExtractDepth
		bind:tavilyApiKey
		bind:tavilyMaxConcurrentRequests
		bind:perplexityApiKey
		bind:perplexityModel
		bind:perplexitySearchContextUsage
		bind:perplexityTemperature
		bind:perplexityImageResultsEnabled
		bind:perplexityMaxConcurrentRequests
		models={ctx.models}
		providers={ctx.providers}
		isFetchingModels={ctx.isFetchingModels}
		modelsError={ctx.modelsError}
	/>
</div>
