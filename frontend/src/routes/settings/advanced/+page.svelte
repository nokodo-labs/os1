<script lang="ts">
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
	import CheckBox from '$lib/components/icons/CheckBox.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import Download from '$lib/components/icons/Download.svelte'
	import FinderFolder from '$lib/components/icons/FinderFolder.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import Users from '$lib/components/icons/Users.svelte'
	import Wrench from '$lib/components/icons/Wrench.svelte'
	import { Switch } from '$lib/components/primitives'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { accentColors, type AccentColorKey } from '$lib/contexts/themeContext.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import { slide } from 'svelte/transition'

	let owuiExpanded = $state(false)
	let owuiHost = $state('')
	let owuiJwt = $state('')

	interface DataAction {
		label: string
		description: string
		icon: typeof Download
		variant: 'default' | 'danger'
		action: () => void
	}

	const exportActions: DataAction[] = [
		{
			label: 'download all chats',
			description: 'export all your conversations as JSON',
			icon: Download,
			variant: 'default',
			action: () => {},
		},
		{
			label: 'download all memories',
			description: 'export all AI memories as JSON',
			icon: Download,
			variant: 'default',
			action: () => {},
		},
		{
			label: 'download all your data',
			description: 'export everything: chats, memories, preferences, and files',
			icon: Download,
			variant: 'default',
			action: () => {},
		},
	]

	const manageActions: DataAction[] = [
		{
			label: 'archive all chats',
			description: 'move all conversations to the archive',
			icon: ArchiveBox,
			variant: 'default',
			action: () => {},
		},
		{
			label: 'delete all chats',
			description: 'permanently remove all conversations',
			icon: Trash,
			variant: 'danger',
			action: () => {},
		},
	]

	// homepage suggestion apps (icons + accents match AppsGrid)
	const suggestionApps = [
		{
			key: 'chats' as const,
			label: 'chats',
			description: 'recent conversations',
			icon: ChatBubbles,
			accent: 'green' as AccentColorKey,
		},
		{
			key: 'reminders' as const,
			label: 'reminders',
			description: 'upcoming reminders',
			icon: CheckBox,
			accent: 'reminders' as AccentColorKey,
		},
		{
			key: 'notes' as const,
			label: 'notes',
			description: 'your notes',
			icon: Document,
			accent: 'notes' as AccentColorKey,
		},
		{
			key: 'friends' as const,
			label: 'friends',
			description: 'contacts and people',
			icon: Users,
			accent: 'purple' as AccentColorKey,
		},
		{
			key: 'library' as const,
			label: 'library',
			description: 'saved content',
			icon: FinderFolder,
			accent: 'yellow' as AccentColorKey,
		},
		{
			key: 'calendar' as const,
			label: 'calendar',
			description: 'events and schedule',
			icon: Calendar,
			accent: 'blue' as AccentColorKey,
		},
	]

	function toggleSuggestionApp(key: keyof typeof preferences.data.homepage): void {
		const current = preferences.data.homepage[key]
		void preferences.update('homepage', { [key]: !current })
	}

	const svgLiquidGlassEnabled = $derived(preferences.data.advanced.svgLiquidGlass ?? false)
	const svgLiquidGlassIslandEnabled = $derived(
		preferences.data.advanced.svgLiquidGlassIsland ?? true
	)
	const svgLiquidMetalEnabled = $derived(preferences.data.advanced.svgLiquidMetal ?? false)

	function setSvgLiquidGlass(enabled: boolean): void {
		void preferences.update('advanced', { svgLiquidGlass: enabled })
	}

	function setSvgLiquidGlassIsland(enabled: boolean): void {
		void preferences.update('advanced', { svgLiquidGlassIsland: enabled })
	}

	function setSvgLiquidMetal(enabled: boolean): void {
		void preferences.update('advanced', { svgLiquidMetal: enabled })
	}
</script>

<SettingsSectionLayout
	icon={Wrench}
	label="advanced"
	description="data management, imports, and danger zone"
>
	<div class="space-y-4">
		<!-- experimental features -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-foreground/85">experimental features</div>
			<div class="mt-1 text-sm text-foreground/55">
				these features are experimental and may cause performance issues or bugs.
			</div>

			<div class="mt-6 flex items-center justify-between">
				<div>
					<span id="svg-liquid-glass-label" class="text-sm text-foreground/70"
						>enable svg liquid glass globally</span
					>
					<div class="mt-1 text-xs text-foreground/40">
						use svg-based liquid glass effects everywhere when your browser supports it.
						this can be very heavy on performance.
					</div>
				</div>
				<Switch
					size="md"
					checked={svgLiquidGlassEnabled}
					onchange={setSvgLiquidGlass}
					ariaLabelledbyId="svg-liquid-glass-label"
				/>
			</div>

			<div class="mt-6 flex items-center justify-between">
				<div>
					<span id="svg-liquid-glass-island-label" class="text-sm text-foreground/70"
						>enable svg liquid glass for island</span
					>
					<div class="mt-1 text-xs text-foreground/40">
						use svg-based liquid glass effects specifically for the island component.
					</div>
				</div>
				<Switch
					size="md"
					checked={svgLiquidGlassIslandEnabled}
					onchange={setSvgLiquidGlassIsland}
					ariaLabelledbyId="svg-liquid-glass-island-label"
				/>
			</div>

			<div class="mt-6 flex items-center justify-between">
				<div>
					<span id="svg-liquid-metal-label" class="text-sm text-foreground/70"
						>enable svg liquid metal</span
					>
					<div class="mt-1 text-xs text-foreground/40">
						use svg-based liquid metal edge refractions when supported by your browser.
					</div>
				</div>
				<Switch
					size="md"
					checked={svgLiquidMetalEnabled}
					onchange={setSvgLiquidMetal}
					ariaLabelledbyId="svg-liquid-metal-label"
				/>
			</div>
		</div>

		<!-- homepage suggestions -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-foreground">homepage suggestions</div>
			<div class="mt-1 text-sm text-foreground/50">
				choose which apps appear when you search on the home screen.
			</div>
			<div class="mt-4 space-y-2">
				{#each suggestionApps as app (app.key)}
					{@const Icon = app.icon}
					{@const enabled = preferences.data.homepage[app.key]}
					{@const color = accentColors[app.accent]?.primary}
					<label
						class="rounded-pill flex w-full cursor-pointer items-center gap-3 border border-foreground/10 px-4 py-3 text-left text-sm transition-all hover:border-foreground/15 {enabled
							? 'bg-foreground/5'
							: 'bg-foreground/2'}"
					>
						<div
							class="rounded-pill flex h-8 w-8 shrink-0 items-center justify-center"
							style={enabled && color ? `color: ${color};` : ''}
						>
							<Icon
								class="h-4.5 w-4.5"
								variant="solid"
								style={enabled ? '' : 'opacity: 0.3;'}
							/>
						</div>
						<div class="min-w-0 flex-1">
							<div class="font-medium {enabled ? 'text-foreground/80' : 'text-foreground/40'}">
								{app.label}
							</div>
							<div class="text-xs text-foreground/50">{app.description}</div>
						</div>
						<Switch
							checked={enabled ?? true}
							size="sm"
							onchange={() => toggleSuggestionApp(app.key)}
						/>
					</label>
				{/each}
			</div>
		</div>

		<!-- data export -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-foreground">data export</div>
			<div class="mt-1 text-sm text-foreground/50">download your data in portable formats.</div>
			<div class="mt-4 space-y-2">
				{#each exportActions as action (action.label)}
					{@const Icon = action.icon}
					<button
						type="button"
						disabled
						class="rounded-pill flex w-full items-center gap-3 border border-foreground/10 bg-foreground/3 px-4 py-3 text-left text-sm transition-all hover:border-foreground/15 hover:bg-foreground/5 disabled:opacity-50"
					>
						<Icon class="h-4.5 w-4.5 shrink-0 text-foreground/50" />
						<div class="min-w-0 flex-1">
							<div class="font-medium text-foreground/80">{action.label}</div>
							<div class="text-xs text-foreground/50">{action.description}</div>
						</div>
						<span
							class="rounded-pill bg-foreground/5 px-2 py-0.5 text-[0.65rem] text-foreground/45"
							>soon</span
						>
					</button>
				{/each}
			</div>
		</div>

		<!-- chat management -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-foreground">chat management</div>
			<div class="mt-1 text-sm text-foreground/50">organize or clean up your conversations.</div>
			<div class="mt-4 space-y-2">
				{#each manageActions as action (action.label)}
					{@const Icon = action.icon}
					<button
						type="button"
						disabled
						class="rounded-pill flex w-full items-center gap-3 border px-4 py-3 text-left text-sm transition-all disabled:opacity-50
							{action.variant === 'danger'
							? 'border-red-500/20 bg-red-500/5 hover:border-red-500/30 hover:bg-red-500/10'
							: 'border-foreground/10 bg-foreground/3 hover:border-foreground/15 hover:bg-foreground/5'}"
					>
						<Icon
							class="h-4.5 w-4.5 shrink-0 {action.variant === 'danger'
								? 'text-red-400/60'
								: 'text-foreground/50'}"
						/>
						<div class="min-w-0 flex-1">
							<div
								class="font-medium {action.variant === 'danger'
									? 'text-red-400/80'
									: 'text-foreground/80'}"
							>
								{action.label}
							</div>
							<div class="text-xs text-foreground/50">{action.description}</div>
						</div>
						<span
							class="rounded-pill bg-foreground/5 px-2 py-0.5 text-[0.65rem] text-foreground/45"
							>soon</span
						>
					</button>
				{/each}
			</div>
		</div>

		<!-- open webui import -->
		<div class="rounded-container liquid-glass liquid-glass--frosted">
			<button
				type="button"
				class="flex w-full cursor-pointer items-center justify-between border-none bg-transparent p-5 text-left"
				onclick={() => (owuiExpanded = !owuiExpanded)}
			>
				<div>
					<div class="text-sm font-semibold text-foreground">open webui import</div>
					<div class="mt-1 text-sm text-foreground/50">
						import data from an open webui instance.
					</div>
				</div>
				<ChevronDown
					class="h-4.5 w-4.5 text-foreground/50 transition-transform duration-200 {owuiExpanded
						? 'rotate-180'
						: ''}"
				/>
			</button>

			{#if owuiExpanded}
				<div
					class="border-t border-foreground/14 px-5 pt-4 pb-5"
					transition:slide={{ duration: 200 }}
				>
					<form class="space-y-3" onsubmit={(e) => e.preventDefault()} autocomplete="off">
						<div>
							<label
								class="mb-1.5 block text-xs font-medium text-foreground/50"
								for="owui-host">host URL</label
							>
							<input
								id="owui-host"
								type="url"
								class="rounded-pill w-full border border-foreground/10 bg-foreground/5 px-4 py-2.5 text-sm text-foreground/90 placeholder:text-foreground/40 transition-colors outline-none focus:border-foreground/20 focus:bg-foreground/8"
								placeholder="https://your-open-webui.example.com"
								bind:value={owuiHost}
							/>
						</div>
						<div>
							<label
								class="mb-1.5 block text-xs font-medium text-foreground/50"
								for="owui-jwt">JWT token</label
							>
							<input
								id="owui-jwt"
								type="password"
								autocomplete="off"
								class="rounded-pill w-full border border-foreground/10 bg-foreground/5 px-4 py-2.5 text-sm text-foreground/90 placeholder:text-foreground/40 transition-colors outline-none focus:border-foreground/20 focus:bg-foreground/8"
								placeholder="paste your open webui JWT here"
								bind:value={owuiJwt}
							/>
						</div>

						<div class="flex gap-2 pt-1">
							<button
								type="button"
								disabled
								class="rounded-pill flex-1 border border-foreground/10 bg-foreground/5 px-3 py-2 text-sm text-foreground/50 transition-colors disabled:opacity-50"
							>
								import all chats
							</button>
							<button
								type="button"
								disabled
								class="rounded-pill flex-1 border border-foreground/10 bg-foreground/5 px-3 py-2 text-sm text-foreground/50 transition-colors disabled:opacity-50"
							>
								import all memories
							</button>
						</div>
						<p class="text-xs text-foreground/45">coming soon</p>
					</form>

					<div class="mt-5 border-t border-foreground/14 pt-4">
						<div class="text-xs font-medium text-foreground/50">
							more imports coming soon
						</div>
						<div class="mt-2 flex flex-wrap gap-2">
							{#each ['ChatGPT', 'Claude', 'Gemini', 'LibreChat'] as platform (platform)}
								<span
									class="rounded-pill border border-foreground/14 bg-foreground/3 px-3 py-1 text-xs text-foreground/45"
								>
									{platform}
								</span>
							{/each}
						</div>
					</div>
				</div>
			{/if}
		</div>

		<!-- danger zone -->
		<div class="rounded-container border border-red-500/20 bg-red-500/5 p-5">
			<div class="flex items-center gap-2">
				<Trash class="h-4.5 w-4.5 text-red-400/70" />
				<div class="text-sm font-semibold text-red-400">danger zone</div>
			</div>
			<div class="mt-1 text-sm text-foreground/50">
				irreversible actions. proceed with extreme caution.
			</div>
			<div class="mt-4">
				<button
					type="button"
					disabled
					class="rounded-pill border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-400 transition-colors hover:bg-red-500/20 disabled:opacity-50"
				>
					delete account
				</button>
				<p class="mt-2 text-xs text-foreground/45">
					this will permanently delete your account and all associated data. coming soon.
				</p>
			</div>
		</div>
	</div>
</SettingsSectionLayout>
