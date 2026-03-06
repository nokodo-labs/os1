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

	type SearchAgent = 'native' | 'perplexity'
	type SearchEngine = 'google' | 'searxng'
	type WebLoaderEngine = 'native' | 'tavily' | 'playwright'
	type PerplexityModel =
		| 'sonar'
		| 'sonar-pro'
		| 'sonar-reasoning'
		| 'sonar-reasoning-pro'
		| 'sonar-deep-research'
	type SearchContextUsage = 'low' | 'medium' | 'high'
	type SearchRecencyFilter = 'month' | 'week' | 'day' | 'hour'

	type Props = {
		// top-level
		searchAgent?: SearchAgent
		blacklistedDomains?: string
		// search engines
		engineEngine?: SearchEngine
		searxngInstanceUrl?: string
		searxngMaxResults?: string
		searxngMaxConcurrentRequests?: string
		searxngTimeoutSeconds?: string
		// web loaders
		webLoaderEngine?: WebLoaderEngine
		webLoaderTimeoutSeconds?: string
		webLoaderUserAgent?: string
		tavilyExtractDepth?: 'basic' | 'advanced'
		tavilyApiKey?: string
		tavilyMaxConcurrentRequests?: string
		// perplexity
		perplexityApiKey?: string
		perplexityModel?: PerplexityModel
		perplexitySearchContextUsage?: SearchContextUsage
		perplexityTemperature?: string
		perplexitySearchRecencyFilter?: SearchRecencyFilter | ''
		perplexityReturnImages?: boolean
		perplexityMaxConcurrentRequests?: string
	}

	let {
		searchAgent = $bindable<SearchAgent>('native'),
		blacklistedDomains = $bindable(''),
		engineEngine = $bindable<SearchEngine>('searxng'),
		searxngInstanceUrl = $bindable(''),
		searxngMaxResults = $bindable(''),
		searxngMaxConcurrentRequests = $bindable(''),
		searxngTimeoutSeconds = $bindable(''),
		webLoaderEngine = $bindable<WebLoaderEngine>('native'),
		webLoaderTimeoutSeconds = $bindable(''),
		webLoaderUserAgent = $bindable(''),
		tavilyExtractDepth = $bindable<'basic' | 'advanced'>('advanced'),
		tavilyApiKey = $bindable(''),
		tavilyMaxConcurrentRequests = $bindable(''),
		perplexityApiKey = $bindable(''),
		perplexityModel = $bindable<PerplexityModel>('sonar'),
		perplexitySearchContextUsage = $bindable<SearchContextUsage>('medium'),
		perplexityTemperature = $bindable(''),
		perplexitySearchRecencyFilter = $bindable<SearchRecencyFilter | ''>(''),
		perplexityReturnImages = $bindable(false),
		perplexityMaxConcurrentRequests = $bindable(''),
	}: Props = $props()
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>web search</CardTitle>
		<CardDescription>search engine, web loader, and agentic search settings.</CardDescription>
	</CardHeader>
	<CardContent class="space-y-5">
		<!-- top-level -->
		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<Label for="ws_search_agent">search agent</Label>
				<p class="text-xs text-zinc-500">agent used for the agentic web search tool.</p>
				<Select
					value={searchAgent}
					onValueChange={(v: string) => (searchAgent = v as SearchAgent)}
				>
					<SelectTrigger id="ws_search_agent" class="rounded-xl">
						<span class="truncate text-left">{searchAgent}</span>
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="native">native</SelectItem>
						<SelectItem value="perplexity">perplexity</SelectItem>
					</SelectContent>
				</Select>
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

		<!-- search engines -->
		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<p class="mb-4 text-sm font-medium">search engine</p>
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="ws_engine_engine">engine</Label>
					<p class="text-xs text-zinc-500">search engine backend for web search.</p>
					<Select
						value={engineEngine}
						onValueChange={(v: string) => (engineEngine = v as SearchEngine)}
					>
						<SelectTrigger id="ws_engine_engine" class="rounded-xl">
							<span class="truncate text-left">{engineEngine}</span>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="google">google</SelectItem>
							<SelectItem value="searxng">searxng</SelectItem>
						</SelectContent>
					</Select>
				</div>
			</div>

			{#if engineEngine === 'searxng'}
				<div class="mt-4 grid gap-4 md:grid-cols-2">
					<div class="space-y-2">
						<Label for="ws_searxng_url">searxng instance url</Label>
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
							bind:value={searxngTimeoutSeconds}
							class="rounded-xl"
						/>
					</div>
				</div>
			{/if}
		</div>

		<!-- web loaders -->
		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<p class="mb-4 text-sm font-medium">web loader</p>
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="ws_loader_engine">engine</Label>
					<p class="text-xs text-zinc-500">backend for fetching and parsing web pages.</p>
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
						bind:value={webLoaderTimeoutSeconds}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2 md:col-span-2">
					<Label for="ws_loader_ua">user agent</Label>
					<Input
						id="ws_loader_ua"
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

		<!-- perplexity -->
		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<p class="mb-4 text-sm font-medium">perplexity</p>
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
					<p class="text-xs text-zinc-500">low = faster/cheaper, high = more thorough.</p>
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
					<p class="text-xs text-zinc-500">lower = more factual (0–2).</p>
					<Input
						id="ws_px_temperature"
						type="number"
						step="0.05"
						min="0"
						max="2"
						bind:value={perplexityTemperature}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="ws_px_recency">search recency filter</Label>
					<p class="text-xs text-zinc-500">
						restrict results to a time window (none = all).
					</p>
					<Select
						value={perplexitySearchRecencyFilter}
						onValueChange={(v: string) =>
							(perplexitySearchRecencyFilter = v as SearchRecencyFilter | '')}
					>
						<SelectTrigger id="ws_px_recency" class="rounded-xl">
							<span class="truncate text-left">
								{perplexitySearchRecencyFilter || 'none'}
							</span>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="">none</SelectItem>
							<SelectItem value="hour">hour</SelectItem>
							<SelectItem value="day">day</SelectItem>
							<SelectItem value="week">week</SelectItem>
							<SelectItem value="month">month</SelectItem>
						</SelectContent>
					</Select>
				</div>
				<div class="space-y-2">
					<Label for="ws_px_concurrent">max concurrent requests</Label>
					<Input
						id="ws_px_concurrent"
						type="number"
						min="1"
						bind:value={perplexityMaxConcurrentRequests}
						class="rounded-xl"
					/>
				</div>
				<div class="flex items-center justify-between">
					<div>
						<Label for="ws_px_images">return images</Label>
						<p class="text-xs text-zinc-500">include image URLs in results.</p>
					</div>
					<Switch
						id="ws_px_images"
						checked={perplexityReturnImages}
						onCheckedChange={(v: boolean) => (perplexityReturnImages = v)}
					/>
				</div>
			</div>
		</div>
	</CardContent>
</Card>
