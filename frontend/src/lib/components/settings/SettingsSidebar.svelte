<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import FloatingScrollTopButton from '$lib/components/FloatingScrollTopButton.svelte'
	import Cog6 from '$lib/components/icons/Cog6.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import MasterSidebarHeader from '$lib/components/layouts/MasterSidebarHeader.svelte'
	import ScrollTopShadow from '$lib/components/ScrollTopShadow.svelte'
	import SidebarListItem from '$lib/components/SidebarListItem.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { FIELD_REVEAL_WAIT_MS, revealSettingsField } from './fieldFocus'
	import { searchSettings } from './searchIndex'
	import { settingsSections, type SettingsSectionDef, type SettingsSectionId } from './sections'

	interface Props {
		selectedSection: string | null
		isMobile?: boolean
		rowIconBackground?: boolean
	}

	let { selectedSection, isMobile = false, rowIconBackground = false }: Props = $props()
	let scrollEl = $state<HTMLElement | null>(null)
	let query = $state('')

	const showAdminDebug = $derived(Boolean(session.currentUser?.is_superuser))

	const effectiveSections = $derived(
		settingsSections.filter((section) => !section.adminOnly || showAdminDebug)
	)

	const trimmedQuery = $derived(query.trim())
	const results = $derived(searchSettings(trimmedQuery, effectiveSections))

	const navOptions = { keepFocus: true, noScroll: true }

	async function openSection(sectionId: SettingsSectionId): Promise<void> {
		switch (sectionId) {
			case 'appearance':
				await goto(resolve('/settings/appearance'), navOptions)
				break
			case 'notifications':
				await goto(resolve('/settings/notifications'), navOptions)
				break
			case 'privacy':
				await goto(resolve('/settings/privacy'), navOptions)
				break
			case 'accessibility':
				await goto(resolve('/settings/accessibility'), navOptions)
				break
			case 'ai':
				await goto(resolve('/settings/ai'), navOptions)
				break
			case 'security':
				await goto(resolve('/settings/security'), navOptions)
				break
			case 'integrations':
				await goto(resolve('/settings/integrations'), navOptions)
				break
			case 'advanced':
				await goto(resolve('/settings/advanced'), navOptions)
				break
			case 'about':
				await goto(resolve('/settings/about'), navOptions)
				break
			case 'debug':
				await goto(resolve('/settings/debug'), navOptions)
				break
		}
	}

	async function selectSection(sectionId: SettingsSectionId, fieldId?: string): Promise<void> {
		await openSection(sectionId)
		// the section is mounted by now, so the field is either registered or
		// still rendering; the reveal waits either way.
		if (fieldId) void revealSettingsField(fieldId, { wait: FIELD_REVEAL_WAIT_MS })
	}

	function prefetchSection(sectionId: string): void {
		void sectionId
		// no-op for now; could prefetch section data if needed
	}
</script>

{#snippet sectionIcon(section: SettingsSectionDef, solid: boolean)}
	<span
		class="rounded-pill text-foreground/80 flex h-8 w-8 items-center justify-center {rowIconBackground
			? 'bg-foreground/8'
			: ''}"
	>
		<section.icon variant={solid || isMobile ? 'solid' : 'outline'} class="h-5 w-5" />
	</span>
{/snippet}

{#snippet sectionRow(section: SettingsSectionDef)}
	<div class="px-3">
		<SidebarListItem
			selected={selectedSection === section.id}
			onSelect={() => selectSection(section.id)}
			onPrefetch={() => prefetchSection(section.id)}
			showChevron={true}
		>
			{#snippet leading()}
				{@render sectionIcon(section, selectedSection === section.id)}
			{/snippet}
			<span class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium"
				>{section.label}</span
			>
		</SidebarListItem>
	</div>
{/snippet}

{#snippet searchField()}
	<div class="px-3 pb-2">
		<div class="relative">
			<Search
				class="text-foreground/40 pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2"
			/>
			<input
				type="text"
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full border py-2 pr-9 pl-9 text-sm transition-colors outline-none"
				placeholder="search settings"
				aria-label="search settings"
				bind:value={query}
			/>
			{#if query}
				<button
					type="button"
					class="rounded-circle text-foreground/40 hover:bg-foreground/10 hover:text-foreground/70 absolute top-1/2 right-2 flex h-6 w-6 -translate-y-1/2 cursor-pointer items-center justify-center transition-colors"
					onclick={() => (query = '')}
					aria-label="clear search"
				>
					<XMark class="h-3.5 w-3.5" />
				</button>
			{/if}
		</div>
	</div>
{/snippet}

<div class="flex h-full min-h-0 flex-col">
	{#if !isMobile}
		<MasterSidebarHeader icon={Cog6} label="settings" iconColor="text-foreground/70" />
		{@render searchField()}
	{/if}

	<div class="relative min-h-0 flex-1 overflow-hidden">
		<nav
			bind:this={scrollEl}
			class="h-full min-h-0 w-full overflow-y-auto {isMobile ? 'pb-10' : 'pt-2 pb-6'}"
		>
			<div class="flex flex-col gap-1">
				{#if isMobile}
					<MasterSidebarHeader
						icon={Cog6}
						label="settings"
						iconColor="text-foreground/70"
						isMobile
					/>
					{@render searchField()}
				{/if}

				{#if trimmedQuery}
					{#if results.length === 0}
						<EmptyState label="no settings found" compact={true} />
					{:else}
						{#each results as group (group.section.id)}
							<div
								class="text-foreground/45 px-6 pt-3 pb-1 text-xs font-medium tracking-wide"
							>
								{group.section.label}
							</div>
							{#if group.sectionMatched}
								{@render sectionRow(group.section)}
							{/if}
							{#each group.fields as field (field.id)}
								<div class="px-3">
									<SidebarListItem
										onSelect={() => selectSection(group.section.id, field.id)}
										showChevron={true}
									>
										{#snippet leading()}
											{@render sectionIcon(group.section, false)}
										{/snippet}
										<span
											class="text-foreground/90 block min-w-0 truncate text-[0.95rem] font-medium"
											>{field.label}</span
										>
										{#if field.description}
											<span
												class="text-foreground/50 mt-0.5 block min-w-0 truncate text-xs"
												>{field.description}</span
											>
										{/if}
									</SidebarListItem>
								</div>
							{/each}
						{/each}
					{/if}
				{:else}
					{#each effectiveSections as section (section.id)}
						{@render sectionRow(section)}
					{/each}
				{/if}
			</div>
		</nav>
		{#if !isMobile}
			<ScrollTopShadow target={scrollEl} />
		{/if}
		<FloatingScrollTopButton target={scrollEl} />
	</div>
</div>
