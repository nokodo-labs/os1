<script lang="ts">
	import { Button } from '$lib/components/ui/button'
	import { BookOpen, Check, Copy } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	let {
		open = $bindable(false),
	}: {
		open?: boolean
	} = $props()

	let copiedVar = $state<string | null>(null)
	let copyTimeout: ReturnType<typeof setTimeout> | undefined

	type Variable = { name: string; description: string }
	type Category = { label: string; description: string; variables: Variable[] }

	const categories: Category[] = [
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
				{ name: 'user_personality', description: 'AI personality preference' },
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
			description: "date/time in the user's local timezone (falls back to UTC)",
			variables: [
				{ name: 'current_date', description: 'date — YYYY-MM-DD' },
				{ name: 'current_date_full', description: 'date — January 15, 2025' },
				{ name: 'current_date_short', description: 'date — 2025-01-15' },
				{ name: 'current_date_weekday', description: 'date — Wednesday, January 15' },
				{
					name: 'current_date_weekday_full',
					description: 'date — Wednesday, January 15, 2025',
				},
				{ name: 'current_date_month_day', description: 'date — January 15' },
				{ name: 'current_day', description: 'day of week — Wednesday' },
				{ name: 'current_time', description: 'time — HH:MM (24h)' },
				{ name: 'current_time_12h', description: 'time — 2:30 PM' },
				{ name: 'current_time_24h', description: 'time — 14:30' },
				{ name: 'current_time_seconds', description: 'time — 14:30:00' },
				{ name: 'current_datetime', description: 'ISO 8601 datetime' },
				{
					name: 'current_datetime_full',
					description: 'full — Wednesday, January 15, 2025 at 2:30 PM',
				},
				{ name: 'current_datetime_short', description: 'short — 2025-01-15 14:30' },
			],
		},
		{
			label: 'server date/time',
			description: 'date/time in UTC (always available)',
			variables: [
				{ name: 'server_date', description: 'date — YYYY-MM-DD' },
				{ name: 'server_date_full', description: 'date — January 15, 2025' },
				{ name: 'server_date_short', description: 'date — 2025-01-15' },
				{ name: 'server_date_weekday', description: 'date — Wednesday, January 15' },
				{
					name: 'server_date_weekday_full',
					description: 'date — Wednesday, January 15, 2025',
				},
				{ name: 'server_date_month_day', description: 'date — January 15' },
				{ name: 'server_day', description: 'day of week — Wednesday' },
				{ name: 'server_time', description: 'time — HH:MM (24h)' },
				{ name: 'server_time_12h', description: 'time — 2:30 PM' },
				{ name: 'server_time_24h', description: 'time — 14:30' },
				{ name: 'server_time_seconds', description: 'time — 14:30:00' },
				{ name: 'server_datetime', description: 'ISO 8601 datetime' },
				{
					name: 'server_datetime_full',
					description: 'full — Wednesday, January 15, 2025 at 2:30 PM',
				},
				{ name: 'server_datetime_short', description: 'short — 2025-01-15 14:30' },
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
				{ name: 'client_is_mobile', description: 'true/false or N/A' },
				{ name: 'client_pwa_installed', description: 'true/false or N/A' },
			],
		},
	]

	function varSyntax(name: string): string {
		return `{{ ${name} }}`
	}

	function copyVariable(name: string) {
		const text = varSyntax(name)
		navigator.clipboard.writeText(text)
		copiedVar = name
		clearTimeout(copyTimeout)
		copyTimeout = setTimeout(() => {
			copiedVar = null
		}, 1500)
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
						{categories.reduce((sum, c) => sum + c.variables.length, 0)} variables available
					</span>
					<Button variant="outline" class="rounded-xl" onclick={() => (open = false)}>
						close
					</Button>
				</div>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
