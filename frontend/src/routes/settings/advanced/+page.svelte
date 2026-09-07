<script lang="ts">
	import { browser } from '$app/environment'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import Download from '$lib/components/icons/Download.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import Wrench from '$lib/components/icons/Wrench.svelte'
	import { ActionButton, Switch } from '$lib/components/primitives'
	import {
		advancedFields,
		homepageSuggestionApps,
		type HomepageSuggestionKey,
	} from '$lib/components/settings/fields/advanced'
	import type { SettingsFieldDef } from '$lib/components/settings/fields/types'
	import { settingsFieldAnchor } from '$lib/components/settings/fieldFocus'
	import PreferenceScopeToggle from '$lib/components/settings/PreferenceScopeToggle.svelte'
	import SettingsField from '$lib/components/settings/SettingsField.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { accentColors, type AccentColorKey } from '$lib/contexts/themeContext.svelte'
	import {
		appVisuals,
		type AppVisualId,
		type ResourceIconComponent,
	} from '$lib/resources/resourceVisuals'
	import { apiCacheStores } from '$lib/stores/apiCacheRegistry'
	import { clearApiCacheStores } from '$lib/stores/cacheLifecycle'
	import { showError } from '$lib/stores/notifications.svelte'
	import { preferences, type ClientPreferenceScope } from '$lib/stores/preferences.svelte'

	interface DataAction {
		field: SettingsFieldDef
		icon: ResourceIconComponent
		variant: 'default' | 'danger'
		action: () => void
	}

	interface SuggestionApp {
		key: HomepageSuggestionKey
		field: SettingsFieldDef
		icon: ResourceIconComponent
		accent: AccentColorKey
	}

	const exportActions: DataAction[] = [
		{
			field: advancedFields.downloadAllChats,
			icon: Download,
			variant: 'default',
			action: () => {},
		},
		{
			field: advancedFields.downloadAllMemories,
			icon: Download,
			variant: 'default',
			action: () => {},
		},
		{
			field: advancedFields.downloadAllData,
			icon: Download,
			variant: 'default',
			action: () => {},
		},
	]

	const manageActions: DataAction[] = [
		{
			field: advancedFields.archiveAllChats,
			icon: ArchiveBox,
			variant: 'default',
			action: () => {},
		},
		{
			field: advancedFields.deleteAllChats,
			icon: Trash,
			variant: 'danger',
			action: () => {},
		},
	]

	function appVisual(id: AppVisualId) {
		return appVisuals.find((app) => app.id === id)
	}

	// labels come from the shared field declarations; the visuals stay here
	const suggestionApps: SuggestionApp[] = homepageSuggestionApps.map((app) => {
		const visual = appVisual(app.appId)
		return {
			key: app.key,
			field: app.field,
			icon: visual?.icon ?? Download,
			accent: visual?.accent ?? 'gray',
		}
	})

	function toggleSuggestionApp(key: HomepageSuggestionKey): void {
		const current = preferences.data.homepage[key]
		void preferences.update('homepage', { [key]: !current })
	}

	const svgLiquidGlassEnabled = $derived(preferences.data.advanced.svgLiquidGlass ?? false)
	const svgLiquidGlassIslandEnabled = $derived(
		preferences.data.advanced.svgLiquidGlassIsland ?? false
	)
	const svgLiquidMetalEnabled = $derived(preferences.data.advanced.svgLiquidMetal ?? false)
	const experimentalUiScope = $derived(preferences.experimentalUiScope)
	let isReloadingApp = $state(false)

	function setSvgLiquidGlass(enabled: boolean): void {
		void preferences.updateExperimentalUi({ svgLiquidGlass: enabled })
	}

	function setSvgLiquidGlassIsland(enabled: boolean): void {
		void preferences.updateExperimentalUi({ svgLiquidGlassIsland: enabled })
	}

	function setSvgLiquidMetal(enabled: boolean): void {
		void preferences.updateExperimentalUi({ svgLiquidMetal: enabled })
	}

	function setExperimentalUiScope(scope: ClientPreferenceScope): void {
		void preferences.setExperimentalUiScope(scope)
	}

	async function reloadApp(): Promise<void> {
		if (!browser || isReloadingApp) return
		isReloadingApp = true
		try {
			clearApiCacheStores(apiCacheStores)
			if ('caches' in window) {
				const cacheNames = await window.caches.keys()
				await Promise.all(cacheNames.map((name) => window.caches.delete(name)))
			}
			window.location.reload()
		} catch {
			isReloadingApp = false
			showError('could not reload app')
		}
	}
</script>

<SettingsSectionLayout
	icon={Wrench}
	label="advanced"
	description="data management, experiments, and danger zone"
>
	<div class="space-y-4">
		<!-- experimental features -->
		<SettingsField field={advancedFields.experimentalFeatures} controlLayout="wrap">
			{#snippet control()}
				<PreferenceScopeToggle
					scope={experimentalUiScope}
					onchange={setExperimentalUiScope}
				/>
			{/snippet}

			<SettingsField
				field={advancedFields.svgLiquidGlass}
				surface="plain"
				size="row"
				class="mt-6"
			>
				{#snippet control(labelId)}
					<Switch
						size="md"
						checked={svgLiquidGlassEnabled}
						onchange={setSvgLiquidGlass}
						ariaLabelledbyId={labelId}
					/>
				{/snippet}
			</SettingsField>

			<SettingsField
				field={advancedFields.svgLiquidGlassIsland}
				surface="plain"
				size="row"
				class="mt-6"
			>
				{#snippet control(labelId)}
					<Switch
						size="md"
						checked={svgLiquidGlassIslandEnabled}
						onchange={setSvgLiquidGlassIsland}
						ariaLabelledbyId={labelId}
					/>
				{/snippet}
			</SettingsField>

			<SettingsField
				field={advancedFields.svgLiquidMetal}
				surface="plain"
				size="row"
				class="mt-6"
			>
				{#snippet control(labelId)}
					<Switch
						size="md"
						checked={svgLiquidMetalEnabled}
						onchange={setSvgLiquidMetal}
						ariaLabelledbyId={labelId}
					/>
				{/snippet}
			</SettingsField>
		</SettingsField>

		<!-- homepage suggestions -->
		<SettingsField field={advancedFields.homepageSuggestions}>
			<div class="mt-4 space-y-2">
				{#each suggestionApps as app (app.key)}
					{@const Icon = app.icon}
					{@const enabled = preferences.data.homepage[app.key]}
					{@const color = accentColors[app.accent]?.primary}
					<label
						class="rounded-pill border-foreground/10 hover:border-foreground/15 flex w-full cursor-pointer items-center gap-3 border px-4 py-3 text-left text-sm transition-all {enabled
							? 'bg-foreground/5'
							: 'bg-foreground/2'}"
						{@attach settingsFieldAnchor(app.field.id)}
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
							<div
								class="font-medium {enabled
									? 'text-foreground/80'
									: 'text-foreground/40'}"
							>
								{app.field.label}
							</div>
							<div class="text-foreground/50 text-xs">{app.field.description}</div>
						</div>
						<Switch
							checked={enabled ?? true}
							size="sm"
							onchange={() => toggleSuggestionApp(app.key)}
						/>
					</label>
				{/each}
			</div>
		</SettingsField>

		<!-- app cache -->
		<SettingsField field={advancedFields.appCache}>
			<ActionButton
				variant="secondary"
				class="mt-4 w-full"
				disabled={isReloadingApp}
				onclick={() => void reloadApp()}
			>
				<ArrowPath class="h-4 w-4" />
				{#if isReloadingApp}
					<ShimmerText className="inline-block">restarting</ShimmerText>
				{:else}
					clear caches and restart app
				{/if}
			</ActionButton>
		</SettingsField>

		<!-- data export -->
		<SettingsField field={advancedFields.dataExport}>
			<div class="mt-4 space-y-2">
				{#each exportActions as action (action.field.id)}
					{@const Icon = action.icon}
					<button
						type="button"
						disabled
						class="rounded-pill border-foreground/10 bg-foreground/3 hover:border-foreground/15 hover:bg-foreground/5 flex w-full items-center gap-3 border px-4 py-3 text-left text-sm transition-all disabled:opacity-50"
						{@attach settingsFieldAnchor(action.field.id)}
					>
						<Icon class="text-foreground/50 h-4.5 w-4.5 shrink-0" />
						<div class="min-w-0 flex-1">
							<div class="text-foreground/80 font-medium">{action.field.label}</div>
							<div class="text-foreground/50 text-xs">{action.field.description}</div>
						</div>
						<span
							class="rounded-pill bg-foreground/5 text-foreground/45 px-2 py-0.5 text-[0.65rem]"
							>soon</span
						>
					</button>
				{/each}
			</div>
		</SettingsField>

		<!-- chat management -->
		<SettingsField field={advancedFields.chatManagement}>
			<div class="mt-4 space-y-2">
				{#each manageActions as action (action.field.id)}
					{@const Icon = action.icon}
					<button
						type="button"
						disabled
						class="rounded-pill flex w-full items-center gap-3 border px-4 py-3 text-left text-sm transition-all disabled:opacity-50
							{action.variant === 'danger'
							? 'border-red-500/20 bg-red-500/5 hover:border-red-500/30 hover:bg-red-500/10'
							: 'border-foreground/10 bg-foreground/3 hover:border-foreground/15 hover:bg-foreground/5'}"
						{@attach settingsFieldAnchor(action.field.id)}
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
								{action.field.label}
							</div>
							<div class="text-foreground/50 text-xs">{action.field.description}</div>
						</div>
						<span
							class="rounded-pill bg-foreground/5 text-foreground/45 px-2 py-0.5 text-[0.65rem]"
							>soon</span
						>
					</button>
				{/each}
			</div>
		</SettingsField>

		<!-- danger zone -->
		<div
			class="rounded-container border border-red-500/20 bg-red-500/5 p-5"
			{@attach settingsFieldAnchor(advancedFields.dangerZone.id)}
		>
			<div class="flex items-center gap-2">
				<Trash class="h-4.5 w-4.5 text-red-400/70" />
				<div class="text-sm font-semibold text-red-400">
					{advancedFields.dangerZone.label}
				</div>
			</div>
			<div class="text-foreground/50 mt-1 text-sm">
				{advancedFields.dangerZone.description}
			</div>
			<div class="mt-4">
				<button
					type="button"
					disabled
					class="rounded-pill border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-400 transition-colors hover:bg-red-500/20 disabled:opacity-50"
				>
					delete account
				</button>
				<p class="text-foreground/45 mt-2 text-xs">
					this will permanently delete your account and all associated data. coming soon.
				</p>
			</div>
		</div>
	</div>
</SettingsSectionLayout>
