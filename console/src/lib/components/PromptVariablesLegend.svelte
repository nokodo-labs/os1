<script lang="ts">
	import { Button } from '$lib/components/ui/button'
	import { BookOpen, Check, Copy, Info } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	let {
		open = $bindable(false),
		prompts = [],
	}: {
		open?: boolean
		prompts?: Array<{ command: string }>
	} = $props()

	let copiedVar = $state<string | null>(null)
	let copyTimeout: ReturnType<typeof setTimeout> | undefined

	type Variable = { name: string; description: string }
	type Category = { label: string; description: string; variables: Variable[] }

	const categories: Category[] = [
		{
			label: 'filter injection points',
			description:
				'variables that activate filters. include them in your system prompt to enable the corresponding filter',
			variables: [
				{
					name: 'user_memories',
					description: 'injects saved user memories (requires memory_context filter)',
				},
				{
					name: 'referenced_attachments',
					description:
						'injects decayed attachment manifest (requires attachment_decay filter)',
				},
			],
		},
		{
			label: 'user profile',
			description: 'information about the authenticated user',
			variables: [
				{ name: 'user_name', description: 'display name or email prefix' },
				{ name: 'user_email', description: 'email address' },
				{ name: 'user_bio', description: 'bio (from AI or account prefs)' },
				{ name: 'user_gender', description: 'gender identity' },
				{ name: 'user_birth_date', description: 'birth date (ISO format)' },
				{ name: 'user_age', description: 'age in years (computed)' },
				{ name: 'user_custom_instructions', description: 'custom AI instructions' },
				{ name: 'ai_personality', description: 'AI personality / tone preference' },
			],
		},
		{
			label: 'user timezone',
			description: "display variants of the user's timezone",
			variables: [
				{
					name: 'user_timezone',
					description: 'IANA timezone name (e.g. America/New_York)',
				},
				{
					name: 'user_timezone_abbr',
					description: 'timezone abbreviation (e.g. EST)',
				},
				{
					name: 'user_utc_offset',
					description: 'UTC offset (e.g. UTC-05:00)',
				},
				{
					name: 'user_timezone_name',
					description: 'timezone full name (e.g. America/New_York)',
				},
			],
		},
		{
			label: 'user date/time',
			description:
				"date/time in the user's local timezone with timezone info (falls back to UTC)",
			variables: [
				{ name: 'current_date', description: 'date - YYYY-MM-DD' },
				{ name: 'current_date_full', description: 'date - January 15, 2025' },
				{ name: 'current_date_short', description: 'date - 2025-01-15' },
				{ name: 'current_date_weekday', description: 'date - Wednesday, January 15' },
				{
					name: 'current_date_weekday_full',
					description: 'date - Wednesday, January 15, 2025',
				},
				{ name: 'current_date_month_day', description: 'date - January 15' },
				{ name: 'current_day', description: 'day of week - Wednesday' },
				{
					name: 'current_time',
					description: 'time - HH:MM with timezone (e.g. 14:30 EST (UTC-05:00))',
				},
				{
					name: 'current_time_12h',
					description: 'time - 2:30 PM with timezone',
				},
				{
					name: 'current_time_24h',
					description: 'time - 14:30 with timezone',
				},
				{
					name: 'current_time_seconds',
					description: 'time - 14:30:00 with timezone',
				},
				{ name: 'current_datetime', description: 'ISO 8601 datetime (includes offset)' },
				{
					name: 'current_datetime_full',
					description: 'full - Wednesday, January 15, 2025 at 2:30 PM EST (UTC-05:00)',
				},
				{
					name: 'current_datetime_short',
					description: 'short - 2025-01-15 14:30 with timezone',
				},
				{
					name: 'current_timezone',
					description: 'timezone label for current_* times (e.g. EST (UTC-05:00))',
				},
			],
		},
		{
			label: 'server date/time',
			description: 'date/time in UTC with timezone info (always available)',
			variables: [
				{ name: 'server_date', description: 'date - YYYY-MM-DD' },
				{ name: 'server_date_full', description: 'date - January 15, 2025' },
				{ name: 'server_date_short', description: 'date - 2025-01-15' },
				{ name: 'server_date_weekday', description: 'date - Wednesday, January 15' },
				{
					name: 'server_date_weekday_full',
					description: 'date - Wednesday, January 15, 2025',
				},
				{ name: 'server_date_month_day', description: 'date - January 15' },
				{ name: 'server_day', description: 'day of week - Wednesday' },
				{
					name: 'server_time',
					description: 'time - HH:MM with timezone (e.g. 19:30 UTC (UTC+00:00))',
				},
				{
					name: 'server_time_12h',
					description: 'time - 7:30 PM with timezone',
				},
				{
					name: 'server_time_24h',
					description: 'time - 19:30 with timezone',
				},
				{
					name: 'server_time_seconds',
					description: 'time - 19:30:00 with timezone',
				},
				{ name: 'server_datetime', description: 'ISO 8601 datetime (includes offset)' },
				{
					name: 'server_datetime_full',
					description: 'full - Wednesday, January 15, 2025 at 7:30 PM UTC (UTC+00:00)',
				},
				{
					name: 'server_datetime_short',
					description: 'short - 2025-01-15 19:30 with timezone',
				},
				{
					name: 'server_timezone',
					description: 'timezone label for server_* times (e.g. UTC (UTC+00:00))',
				},
			],
		},
		{
			label: 'client context',
			description: "device and environment info from the user's browser",
			variables: [
				{
					name: 'client_timezone',
					description: 'IANA timezone (e.g. America/New_York)',
				},
				{
					name: 'client_language',
					description: 'browser language (e.g. en-US)',
				},
				{ name: 'client_os', description: 'operating system (e.g. Windows)' },
				{ name: 'client_browser', description: 'browser name (e.g. Chrome)' },
				{ name: 'client_user_agent', description: 'raw browser user-agent string' },
				{ name: 'client_is_mobile', description: 'true/false or N/A' },
				{ name: 'client_pwa_installed', description: 'true/false or N/A' },
				{ name: 'client_offline', description: 'whether the client is offline or N/A' },
				{
					name: 'client_display_mode',
					description: 'display mode (browser, standalone, fullscreen, etc)',
				},
				{
					name: 'client_preferred_color_scheme',
					description: 'dark/light/no-preference or N/A',
				},
				{
					name: 'client_prefers_reduced_motion',
					description: 'true/false or N/A',
				},
				{ name: 'client_prefers_contrast', description: 'more/less/no-preference or N/A' },
				{ name: 'client_idle_state', description: 'active/idle or N/A' },
				{
					name: 'client_gamepad_count',
					description: 'number of connected gamepads or N/A',
				},
				{ name: 'client_gamepads', description: 'connected gamepad ids, comma-separated' },
				{ name: 'client_connection_type', description: 'network connection type or N/A' },
				{
					name: 'client_connection_effective_type',
					description: 'effective network type (e.g. 4g) or N/A',
				},
				{
					name: 'client_connection_downlink_mbps',
					description: 'estimated downlink speed in Mbps or N/A',
				},
				{
					name: 'client_connection_rtt_ms',
					description: 'estimated round-trip time in milliseconds or N/A',
				},
				{
					name: 'client_connection_save_data',
					description: 'data saver enabled true/false or N/A',
				},
				{
					name: 'client_battery_supported',
					description: 'battery API support true/false or N/A',
				},
				{
					name: 'client_battery_charging',
					description: 'charging state true/false or N/A',
				},
				{ name: 'client_battery_level', description: 'battery level percentage or N/A' },
				{
					name: 'client_battery_charging_time_seconds',
					description: 'seconds until full charge or N/A',
				},
				{
					name: 'client_battery_discharging_time_seconds',
					description: 'seconds until empty or N/A',
				},
			],
		},
		{
			label: 'user location',
			description:
				'geolocation from the browser (requires user permission + use location enabled)',
			variables: [
				{
					name: 'client_latitude',
					description: 'latitude coordinate (e.g. 37.7749)',
				},
				{
					name: 'client_longitude',
					description: 'longitude coordinate (e.g. -122.4194)',
				},
				{
					name: 'client_location',
					description: 'human-readable location label if available',
				},
			],
		},
	]

	function varSyntax(name: string): string {
		return `{{ ${name} }}`
	}

	function includeSyntax(command: string): string {
		return `{% include '${command}' %}`
	}

	function copyText(text: string, key: string) {
		navigator.clipboard.writeText(text)
		copiedVar = key
		clearTimeout(copyTimeout)
		copyTimeout = setTimeout(() => {
			copiedVar = null
		}, 1500)
	}

	function copyVariable(name: string) {
		copyText(varSyntax(name), name)
	}

	function copyPromptInclude(command: string) {
		copyText(includeSyntax(command), `prompt:${command}`)
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/50" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[85vh] w-[min(800px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div class="shrink-0 border-b border-zinc-800 p-6 pb-4">
				<Dialog.Title class="flex items-center gap-2 text-lg font-semibold">
					<BookOpen class="h-5 w-5 text-zinc-400" />
					prompt variables
				</Dialog.Title>
				<Dialog.Description class="mt-1 text-sm text-zinc-400">
					use these variables in system prompts and prompt templates with Jinja2 syntax.
					click a variable to copy it. variables without data render as
					<code class="rounded bg-zinc-800 px-1 py-0.5 text-xs">N/A</code>.
				</Dialog.Description>
			</div>

			<div class="flex-1 space-y-6 overflow-y-auto p-6 pt-4">
				<!-- usage instructions -->
				<div
					class="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 text-sm text-zinc-300"
				>
					<h3 class="mb-2 flex items-center gap-2 font-semibold text-zinc-200">
						<Info class="h-4 w-4 text-zinc-400" />
						how to use prompts
					</h3>
					<ul class="list-inside list-disc space-y-1 text-xs text-zinc-400">
						<li>
							<strong>variables</strong>: insert dynamic values with
							<code class="rounded bg-zinc-800 px-1 py-0.5"
								>{'{{ variable_name }}'}</code
							>
						</li>
						<li>
							<strong>include a prompt</strong>: compose prompts by including others
							with
							<code class="rounded bg-zinc-800 px-1 py-0.5"
								>{"{% include 'prompt-name' %}"}</code
							>
						</li>
						<li>
							<strong>legacy syntax</strong>:
							<code class="rounded bg-zinc-800 px-1 py-0.5"
								>{'{{ PROMPTS.prompt-name }}'}</code
							>
							is also supported (auto-converted to include)
						</li>
						<li>
							prompts can include other prompts (composable), but circular references
							are rejected
						</li>
					</ul>
				</div>

				<!-- available prompts as include targets -->
				{#if prompts.length > 0}
					<div>
						<h3 class="text-sm font-semibold text-zinc-200">available prompts</h3>
						<p class="mb-2 text-xs text-zinc-500">
							include these prompts in templates. click to copy the include syntax.
						</p>
						<div
							class="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50"
						>
							{#each prompts as prompt, i}
								<button
									type="button"
									class="flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-zinc-800/60 {i >
									0
										? 'border-t border-zinc-800/60'
										: ''}"
									onclick={() => copyPromptInclude(prompt.command)}
									title="copy {includeSyntax(prompt.command)}"
								>
									<code
										class="shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs text-zinc-300"
									>
										{includeSyntax(prompt.command)}
									</code>
									<span class="min-w-0 flex-1 truncate text-xs text-zinc-400">
										{prompt.command}
									</span>
									<span class="shrink-0 text-zinc-600">
										{#if copiedVar === `prompt:${prompt.command}`}
											<Check class="h-3.5 w-3.5 text-green-400" />
										{:else}
											<Copy class="h-3.5 w-3.5" />
										{/if}
									</span>
								</button>
							{/each}
						</div>
					</div>
				{/if}

				{#each categories as category}
					<div>
						<h3 class="text-sm font-semibold text-zinc-200">{category.label}</h3>
						<p class="mb-2 text-xs text-zinc-500">{category.description}</p>
						<div
							class="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50"
						>
							{#each category.variables as variable, i}
								<button
									type="button"
									class="flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-zinc-800/60 {i >
									0
										? 'border-t border-zinc-800/60'
										: ''}"
									onclick={() => copyVariable(variable.name)}
									title="copy {varSyntax(variable.name)}"
								>
									<code
										class="shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs text-zinc-300"
									>
										{varSyntax(variable.name)}
									</code>
									<span class="min-w-0 flex-1 truncate text-xs text-zinc-400">
										{variable.description}
									</span>
									<span class="shrink-0 text-zinc-600">
										{#if copiedVar === variable.name}
											<Check class="h-3.5 w-3.5 text-green-400" />
										{:else}
											<Copy class="h-3.5 w-3.5" />
										{/if}
									</span>
								</button>
							{/each}
						</div>
					</div>
				{/each}
			</div>

			<div class="shrink-0 border-t border-zinc-800 p-4">
				<div class="flex items-center justify-between">
					<span class="text-xs text-zinc-500">
						{categories.reduce((sum, c) => sum + c.variables.length, 0)} variables
						{#if prompts.length > 0}
							+ {prompts.length} prompts
						{/if}
						available
					</span>
					<Button variant="outline" class="rounded-xl" onclick={() => (open = false)}>
						close
					</Button>
				</div>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
