<script lang="ts">
	import { api, type Schemas } from '$lib/api'
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
	import { Switch } from '$lib/components/ui/switch'
	import { Plus, RefreshCw, Save, Trash } from '@lucide/svelte'

	type SettingsResponse = Schemas['SettingsResponse']
	type SettingsUpdateRequest = Schemas['SettingsUpdateRequest']
	type Deployment = Schemas['OpenWebUIDeploymentPatch']
	type IntegrationsSettingsPatch = NonNullable<SettingsUpdateRequest['data']['integrations']>
	type MCPSettingsPatch = NonNullable<IntegrationsSettingsPatch['mcp']>
	type MCPOriginMode = 'allow' | 'deny'
	type MCPTransport = NonNullable<Schemas['MCPIntegrationSettings']['allowed_transports']>[number]

	const mcpTransportOptions: {
		value: MCPTransport
		label: string
		description: string
	}[] = [
		{
			value: 'streamable_http',
			label: 'streamable HTTP',
			description: 'current remote HTTP transport for MCP servers',
		},
		{
			value: 'sse',
			label: 'SSE',
			description: 'older HTTP + Server-Sent Events transport',
		},
		{
			value: 'stdio',
			label: 'stdio',
			description: 'local process transport for command-based servers',
		},
	]

	const emptySettingsVersions: Schemas['SettingsVersions'] = {
		ui: 0,
		ai: 0,
		branding: 0,
		media: 0,
		assets: 0,
		limits: 0,
		security: 0,
		notifications: 0,
		soft_delete: 0,
		web_search: 0,
		code_interpreter: 0,
		default_permissions: 0,
		integrations: 0,
		cache: 0,
		tasks: 0,
	}

	let enabled = $state(true)
	let deployments = $state<Deployment[]>([])
	let mcpEnabled = $state(true)
	let mcpStartupDiscoveryEnabled = $state(false)
	let mcpListChangeListeningEnabled = $state(true)
	let mcpListChangeDebounceSeconds = $state('')
	let mcpListChangeReconnectMaxDelaySeconds = $state('')
	let mcpAllowedTransports = $state<MCPTransport[]>(['streamable_http'])
	let mcpOriginMode = $state<MCPOriginMode>('deny')
	let mcpOrigins = $state('')
	let mcpDefaultTimeoutSeconds = $state('')
	let mcpMaxTimeoutSeconds = $state('')
	let mcpUserServerMaxCount = $state('')
	let mcpUserServerMaxTools = $state('')
	let mcpUserToolDefinitionMaxTokens = $state('')
	let originalSnapshot = $state<string>('')

	let isFetching = $state(true)
	let isSaving = $state(false)
	let error = $state<string | null>(null)
	let success = $state<string | null>(null)

	let expectedVersion = $state<number>(0)

	function snapshot(): string {
		return JSON.stringify({
			enabled,
			deployments,
			mcpEnabled,
			mcpStartupDiscoveryEnabled,
			mcpListChangeListeningEnabled,
			mcpListChangeDebounceSeconds,
			mcpListChangeReconnectMaxDelaySeconds,
			mcpAllowedTransports,
			mcpOriginMode,
			mcpOrigins,
			mcpDefaultTimeoutSeconds,
			mcpMaxTimeoutSeconds,
			mcpUserServerMaxCount,
			mcpUserServerMaxTools,
			mcpUserToolDefinitionMaxTokens,
		})
	}

	const hasChanges = $derived(snapshot() !== originalSnapshot)

	async function load() {
		isFetching = true
		error = null
		success = null
		const result = await api.GET('/v1/settings', {})
		if (result.error) {
			error = 'failed to load settings'
			isFetching = false
			return
		}
		const data: SettingsResponse = result.data
		const owui = data.data.integrations?.open_webui
		enabled = owui?.enabled ?? true
		deployments = (owui?.deployments ?? []).map((deployment) => ({
			name: deployment.name,
			description: String(deployment.description ?? ''),
			origin: deployment.origin,
		}))
		const mcp = data.data.integrations?.mcp
		mcpEnabled = mcp?.enabled ?? true
		mcpStartupDiscoveryEnabled = mcp?.startup_discovery_enabled ?? false
		mcpListChangeListeningEnabled = mcp?.list_change_listening_enabled ?? true
		mcpListChangeDebounceSeconds = String(mcp?.list_change_debounce_seconds ?? '')
		mcpListChangeReconnectMaxDelaySeconds = String(
			mcp?.list_change_reconnect_max_delay_seconds ?? ''
		)
		mcpAllowedTransports = normalizeMcpTransports(mcp?.allowed_transports)
		mcpOriginMode = mcp?.user_server_origin_mode ?? 'deny'
		mcpOrigins = (mcp?.user_server_origins ?? []).join(', ')
		mcpDefaultTimeoutSeconds = String(mcp?.default_timeout_seconds ?? '')
		mcpMaxTimeoutSeconds = String(mcp?.max_timeout_seconds ?? '')
		mcpUserServerMaxCount = String(mcp?.user_server_max_count ?? '')
		mcpUserServerMaxTools = String(mcp?.user_server_max_tools ?? '')
		mcpUserToolDefinitionMaxTokens = String(mcp?.user_tool_definition_max_tokens ?? '')
		expectedVersion = Number(data.versions?.integrations ?? 0)
		originalSnapshot = snapshot()
		isFetching = false
	}

	function addDeployment() {
		deployments = [...deployments, { name: '', description: '', origin: '' }]
	}

	function removeDeployment(idx: number) {
		deployments = deployments.filter((_, i) => i !== idx)
	}

	function validate(): string | null {
		const origins: string[] = []
		for (const [i, d] of deployments.entries()) {
			if (!d.name || !d.description || !d.origin) {
				return `deployment #${i + 1}: name, description, and origin are required`
			}
			let normalizedOrigin: string
			try {
				const url = new URL(d.origin)
				normalizedOrigin = url.origin.toLowerCase()
			} catch {
				return `deployment #${i + 1}: origin must be a valid URL`
			}
			if (origins.includes(normalizedOrigin)) {
				return `deployment #${i + 1}: duplicate origin "${d.origin}"`
			}
			origins.push(normalizedOrigin)
		}
		const numericFields = [
			{
				label: 'MCP list-change debounce',
				value: mcpListChangeDebounceSeconds,
				min: 0.1,
				max: 30,
			},
			{
				label: 'MCP list-change reconnect max delay',
				value: mcpListChangeReconnectMaxDelaySeconds,
				min: 1,
				max: 300,
			},
			{ label: 'MCP default timeout', value: mcpDefaultTimeoutSeconds, min: 1, max: 300 },
			{ label: 'MCP max timeout', value: mcpMaxTimeoutSeconds, min: 1, max: 600 },
			{ label: 'MCP user server limit', value: mcpUserServerMaxCount, min: 0, max: 100 },
			{ label: 'MCP user tool limit', value: mcpUserServerMaxTools, min: 0, max: 500 },
			{
				label: 'MCP tool definition token limit',
				value: mcpUserToolDefinitionMaxTokens,
				min: 256,
				max: 128000,
			},
		] as const
		for (const { label, value, min, max } of numericFields) {
			const parsed = Number(value)
			if (value.trim() && (!Number.isFinite(parsed) || parsed < min || parsed > max)) {
				return `${label} must be between ${min} and ${max}`
			}
		}
		const defaultTimeout = numeric(mcpDefaultTimeoutSeconds)
		const maxTimeout = numeric(mcpMaxTimeoutSeconds)
		if (
			defaultTimeout !== undefined &&
			maxTimeout !== undefined &&
			defaultTimeout > maxTimeout
		) {
			return 'MCP default timeout cannot exceed max timeout'
		}
		if (mcpOriginMode === 'allow' && csv(mcpOrigins).length === 0) {
			return 'MCP origin allow mode requires at least one origin'
		}
		if (mcpAllowedTransports.length === 0) {
			return 'at least one MCP transport must be allowed'
		}
		return null
	}

	function normalizeMcpTransports(transports: MCPTransport[] | undefined): MCPTransport[] {
		const normalized = mcpTransportOptions
			.map((option) => option.value)
			.filter((transport) => (transports ?? ['streamable_http']).includes(transport))
		return normalized.length > 0 ? normalized : ['streamable_http']
	}

	function toggleMcpTransport(transport: MCPTransport, enabled: boolean) {
		if (enabled) {
			mcpAllowedTransports = normalizeMcpTransports([...mcpAllowedTransports, transport])
			return
		}
		if (mcpAllowedTransports.length <= 1 && mcpAllowedTransports.includes(transport)) {
			return
		}
		mcpAllowedTransports = mcpAllowedTransports.filter(
			(optionTransport) => optionTransport !== transport
		)
	}

	function csv(value: string): string[] {
		return value
			.split(',')
			.map((item) => item.trim())
			.filter(Boolean)
	}

	function numeric(value: string): number | undefined {
		return value.trim() ? Number(value) : undefined
	}

	function mcpPatch(): MCPSettingsPatch {
		return {
			enabled: mcpEnabled,
			startup_discovery_enabled: mcpStartupDiscoveryEnabled,
			list_change_listening_enabled: mcpListChangeListeningEnabled,
			list_change_debounce_seconds: numeric(mcpListChangeDebounceSeconds),
			list_change_reconnect_max_delay_seconds: numeric(mcpListChangeReconnectMaxDelaySeconds),
			allowed_transports: mcpAllowedTransports,
			user_server_origin_mode: mcpOriginMode,
			user_server_origins: csv(mcpOrigins),
			default_timeout_seconds: numeric(mcpDefaultTimeoutSeconds),
			max_timeout_seconds: numeric(mcpMaxTimeoutSeconds),
			user_server_max_count: numeric(mcpUserServerMaxCount),
			user_server_max_tools: numeric(mcpUserServerMaxTools),
			user_tool_definition_max_tokens: numeric(mcpUserToolDefinitionMaxTokens),
		}
	}

	async function save() {
		const v = validate()
		if (v) {
			error = v
			return
		}
		isSaving = true
		error = null
		success = null
		const body: SettingsUpdateRequest = {
			data: {
				integrations: {
					open_webui: {
						enabled,
						deployments: deployments.map((d) => ({
							name: d.name,
							description: d.description,
							origin: d.origin,
						})),
					},
					mcp: mcpPatch(),
				},
			},
			expected_versions: { ...emptySettingsVersions, integrations: expectedVersion },
		}
		const result = await api.PATCH('/v1/settings', {
			body,
		})
		if (result.error) {
			if (result.response.status === 409) {
				error = 'integrations were updated elsewhere. reload and try again.'
			} else {
				const detail = (result.error as { detail?: unknown })?.detail
				error = typeof detail === 'string' ? detail : 'failed to save'
			}
			isSaving = false
			return
		}
		const data: SettingsResponse | undefined = result.data
		expectedVersion = Number(data?.versions.integrations ?? expectedVersion + 1)
		originalSnapshot = snapshot()
		success = 'saved'
		isSaving = false
	}

	$effect(() => {
		void load()
	})
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>integrations</CardTitle>
		<CardDescription>third-party connections, imports, and MCP policy.</CardDescription>
	</CardHeader>
	<CardContent class="space-y-5">
		{#if error}
			<div class="rounded-lg border border-red-900/40 bg-red-950/40 p-3 text-sm text-red-200">
				{error}
			</div>
		{/if}
		{#if success}
			<div
				class="rounded-lg border border-emerald-900/40 bg-emerald-950/40 p-3 text-sm text-emerald-200"
			>
				{success}
			</div>
		{/if}

		<div class="flex items-center justify-between gap-4">
			<div class="space-y-1">
				<Label>enable Open WebUI import</Label>
				<p class="text-xs text-zinc-500">
					when off, users cannot trigger imports regardless of configured deployments.
				</p>
			</div>
			<Switch bind:checked={enabled} disabled={isFetching || isSaving} />
		</div>

		<div class="space-y-3">
			<div class="flex items-center justify-between gap-3">
				<div>
					<Label>Open WebUI deployments</Label>
					<p class="mt-1 text-xs text-zinc-500">allowed origins for user imports.</p>
				</div>
				<Button
					size="sm"
					variant="secondary"
					class="rounded-xl"
					onclick={addDeployment}
					disabled={isFetching || isSaving}
				>
					<Plus class="mr-1.5 h-4 w-4" />
					add deployment
				</Button>
			</div>
			{#if deployments.length === 0}
				<p class="text-xs text-zinc-500">no deployments configured.</p>
			{/if}
			{#each deployments as dep, idx (idx)}
				<div class="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4">
					<div class="grid gap-3 md:grid-cols-2">
						<div class="space-y-1">
							<Label for={`owui-name-${idx}`}>name</Label>
							<Input
								id={`owui-name-${idx}`}
								class="rounded-lg"
								placeholder="workspace Open WebUI"
								bind:value={dep.name}
							/>
						</div>
						<div class="space-y-1">
							<Label for={`owui-origin-${idx}`}>origin URL</Label>
							<Input
								id={`owui-origin-${idx}`}
								class="rounded-lg"
								placeholder="https://owui.example.com"
								bind:value={dep.origin}
							/>
						</div>
						<div class="space-y-1 md:col-span-2">
							<Label for={`owui-description-${idx}`}>description</Label>
							<Input
								id={`owui-description-${idx}`}
								class="rounded-lg"
								placeholder="company-hosted Open WebUI workspace"
								bind:value={dep.description}
							/>
						</div>
					</div>
					<div class="mt-3 flex justify-end">
						<Button
							size="sm"
							variant="ghost"
							class="rounded-lg text-red-300 hover:bg-red-950/40 hover:text-red-200"
							onclick={() => removeDeployment(idx)}
						>
							<Trash class="mr-1.5 h-4 w-4" />
							remove
						</Button>
					</div>
				</div>
			{/each}
		</div>

		<div class="space-y-4 rounded-xl border border-zinc-800 bg-zinc-950/40 p-4">
			<div>
				<h3 class="text-sm font-medium text-zinc-100">MCP</h3>
				<p class="mt-1 text-xs text-zinc-500">
					global availability, discovery, upstream change handling, transports, and
					user-managed server policy.
				</p>
			</div>

			<div class="space-y-3">
				<div class="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
					<div class="flex items-center justify-between gap-3">
						<div class="space-y-1">
							<Label>enable MCP</Label>
							<p class="text-xs text-zinc-500">
								master switch for all MCP discovery, catalogs, and runtime access.
							</p>
						</div>
						<Switch bind:checked={mcpEnabled} disabled={isFetching || isSaving} />
					</div>
				</div>
				<div class="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
					<div class="flex items-center justify-between gap-3">
						<div class="space-y-1">
							<Label>startup discovery</Label>
							<p class="text-xs text-zinc-500">
								refresh enabled global server snapshots when the backend starts.
							</p>
						</div>
						<Switch
							bind:checked={mcpStartupDiscoveryEnabled}
							disabled={isFetching || isSaving}
						/>
					</div>
				</div>
				<div class="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
					<div class="flex items-center justify-between gap-3">
						<div class="space-y-1">
							<Label>list-change listening</Label>
							<p class="text-xs text-zinc-500">
								keep long-lived connections open for upstream capability change
								notices.
							</p>
						</div>
						<Switch
							bind:checked={mcpListChangeListeningEnabled}
							disabled={isFetching || isSaving}
						/>
					</div>
				</div>
			</div>

			<div class="space-y-3">
				<div class="space-y-1">
					<Label for="mcp_list_change_debounce">list-change debounce seconds</Label>
					<Input
						id="mcp_list_change_debounce"
						type="number"
						min="0.1"
						max="30"
						step="0.1"
						class="rounded-lg"
						bind:value={mcpListChangeDebounceSeconds}
					/>
					<p class="text-xs text-zinc-500">
						wait before refetching a server snapshot after a list-change notice.
					</p>
				</div>
				<div class="space-y-1">
					<Label for="mcp_list_change_reconnect">
						list-change reconnect max delay seconds
					</Label>
					<Input
						id="mcp_list_change_reconnect"
						type="number"
						min="1"
						max="300"
						class="rounded-lg"
						bind:value={mcpListChangeReconnectMaxDelaySeconds}
					/>
					<p class="text-xs text-zinc-500">
						maximum reconnect backoff for list-change listener connections.
					</p>
				</div>
			</div>

			<div class="space-y-2">
				<Label>allowed MCP transports</Label>
				<p class="text-xs text-zinc-500">
					limits which transport types admins may choose when configuring MCP servers.
				</p>
				<div class="space-y-3">
					{#each mcpTransportOptions as option (option.value)}
						<div class="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
							<div class="flex items-center justify-between gap-3">
								<div class="space-y-1">
									<p class="text-sm font-medium text-zinc-100">{option.label}</p>
									<p class="text-xs text-zinc-500">{option.description}</p>
								</div>
								<Switch
									checked={mcpAllowedTransports.includes(option.value)}
									disabled={isFetching || isSaving}
									onCheckedChange={(checked: boolean) =>
										toggleMcpTransport(option.value, checked)}
								/>
							</div>
						</div>
					{/each}
				</div>
			</div>

			<div class="space-y-2">
				<div class="flex items-center justify-between gap-3">
					<Label for="mcp_user_origins">user-managed server origins</Label>
					<div class="flex rounded-xl border border-zinc-800 bg-zinc-900/60 p-1">
						<button
							type="button"
							class="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors {mcpOriginMode ===
							'allow'
								? 'bg-zinc-700 text-zinc-50'
								: 'text-zinc-400 hover:text-zinc-200'}"
							onclick={() => (mcpOriginMode = 'allow')}
						>
							allow only
						</button>
						<button
							type="button"
							class="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors {mcpOriginMode ===
							'deny'
								? 'bg-zinc-700 text-zinc-50'
								: 'text-zinc-400 hover:text-zinc-200'}"
							onclick={() => (mcpOriginMode = 'deny')}
						>
							block
						</button>
					</div>
				</div>
				<Input
					id="mcp_user_origins"
					class="rounded-lg"
					placeholder={mcpOriginMode === 'allow'
						? 'https://tools.example.com, https://mcp.example.com'
						: 'http://localhost:8080'}
					bind:value={mcpOrigins}
				/>
				<p class="text-xs text-zinc-500">
					deny mode blocks the listed origins. allow mode permits only the listed origins
					and cannot be empty.
				</p>
			</div>

			<div class="space-y-3">
				<div class="space-y-1">
					<Label for="mcp_default_timeout">default timeout seconds</Label>
					<Input
						id="mcp_default_timeout"
						type="number"
						min="1"
						max="300"
						class="rounded-lg"
						bind:value={mcpDefaultTimeoutSeconds}
					/>
					<p class="text-xs text-zinc-500">
						request timeout used when a server does not override it.
					</p>
				</div>
				<div class="space-y-1">
					<Label for="mcp_max_timeout">max timeout seconds</Label>
					<Input
						id="mcp_max_timeout"
						type="number"
						min="1"
						max="600"
						class="rounded-lg"
						bind:value={mcpMaxTimeoutSeconds}
					/>
					<p class="text-xs text-zinc-500">
						upper bound for server-specific MCP request timeouts.
					</p>
				</div>
				<div class="space-y-1">
					<Label for="mcp_user_server_max_count">user-managed servers per user</Label>
					<Input
						id="mcp_user_server_max_count"
						type="number"
						min="0"
						max="100"
						class="rounded-lg"
						bind:value={mcpUserServerMaxCount}
					/>
					<p class="text-xs text-zinc-500">
						per-user cap for user-managed MCP server records. use 0 to allow none.
					</p>
				</div>
				<div class="space-y-1">
					<Label for="mcp_user_server_max_tools">tools per user-managed server</Label>
					<Input
						id="mcp_user_server_max_tools"
						type="number"
						min="0"
						max="500"
						class="rounded-lg"
						bind:value={mcpUserServerMaxTools}
					/>
					<p class="text-xs text-zinc-500">
						maximum discovered tools accepted from one user-managed MCP server.
					</p>
				</div>
				<div class="space-y-1">
					<Label for="mcp_user_tool_tokens"
						>user-managed tool definition token limit</Label
					>
					<Input
						id="mcp_user_tool_tokens"
						type="number"
						min="256"
						max="128000"
						class="rounded-lg"
						bind:value={mcpUserToolDefinitionMaxTokens}
					/>
					<p class="text-xs text-zinc-500">
						maximum estimated tokens for a single user-managed tool definition.
					</p>
				</div>
			</div>
		</div>

		<div class="flex items-center justify-end gap-2 pt-2">
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={load}
				disabled={isFetching || isSaving}
			>
				<RefreshCw class="mr-1.5 h-4 w-4" />
				reload
			</Button>
			<Button
				class="rounded-xl"
				onclick={save}
				disabled={!hasChanges || isFetching || isSaving}
			>
				<Save class="mr-1.5 h-4 w-4" />
				{isSaving ? 'saving...' : 'save'}
			</Button>
		</div>
	</CardContent>
</Card>
