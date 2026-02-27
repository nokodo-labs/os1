<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { groups, type Group } from '$lib/stores/groups.svelte'

	const chrome = useSystemChrome()

	const groupId = $derived(page.params.id ?? '')
	let group = $state<Group | null>(null)
	let isLoading = $state(true)

	$effect(() => {
		if (!groupId) return
		void groups.load().then(() => {
			group = groups.getById(groupId) ?? null
			isLoading = false
		})
	})

	const handleBack = async () => {
		await goto(resolve('/social/groups'), { keepFocus: true, noScroll: true })
	}

	$effect(() => {
		chrome.setContextActions(islandBackAction)
		return () => chrome.setContextActions(null)
	})
</script>

{#snippet islandBackAction()}
	<button
		type="button"
		class="rounded-pill hover:text-foreground flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97]"
		onclick={handleBack}
		aria-label="back to groups"
	>
		<ChevronLeft class="h-5 w-5" strokeWidth="2" />
	</button>
{/snippet}

<div
	class="absolute inset-0 overflow-y-auto"
	style="padding-top: calc(var(--chrome-island-offset, 0px) + var(--spacing-island-content));"
>
	<div
		class="pb-10"
		style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
	>
		{#if isLoading}
			<div class="flex flex-col gap-4 py-6">
				<div class="bg-foreground/5 h-8 w-48 animate-pulse rounded-full"></div>
				<div class="bg-foreground/5 h-4 w-72 animate-pulse rounded-full"></div>
			</div>
		{:else if !group}
			<div class="bg-foreground/5 rounded-2xl p-6 text-center">
				<p class="text-foreground/50 text-sm">group not found</p>
			</div>
		{:else}
			<div class="mb-8 flex items-start gap-4 py-2">
				<div
					class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-(--accent-primary)/15"
				>
					<UserGroup class="h-7 w-7 text-(--accent-primary)" variant="solid" />
				</div>
				<div class="flex flex-col gap-1">
					<h1 class="text-foreground text-xl font-bold">{group.name}</h1>
					{#if group.description}
						<p class="text-foreground/60 text-sm">{group.description}</p>
					{/if}
					<div class="text-foreground/45 mt-1 flex items-center gap-2 text-xs">
						<span>{group.memberships?.length ?? 0} members</span>
						<span class="text-foreground/20">-</span>
						<span>
							created <Timestamp
								timestamp={new Date(group.created_at)}
								mode="relative"
							/>
						</span>
					</div>
				</div>
			</div>

			<section class="flex flex-col gap-3">
				<h2 class="text-foreground/60 text-sm font-semibold">members</h2>

				{#if group.memberships && group.memberships.length > 0}
					<div class="flex flex-col gap-1">
						{#each group.memberships as member (member.id)}
							<button
								class="interactive-subtle hover:bg-foreground/5 flex w-full items-center gap-3 rounded-full p-3 text-left"
								onclick={() => goto(resolve(`/social/users/${member.user_id}`))}
							>
								<div
									class="bg-foreground/10 text-foreground/80 flex h-9 w-9 items-center justify-center rounded-full text-xs font-semibold"
								>
									{member.user_id.slice(0, 2).toUpperCase()}
								</div>
								<div class="flex min-w-0 flex-col">
									<span class="text-foreground truncate text-sm">
										{member.user_id}
									</span>
									<span class="text-foreground/45 text-xs">{member.role}</span>
								</div>
							</button>
						{/each}
					</div>
				{:else}
					<div class="bg-foreground/5 rounded-2xl py-8 text-center">
						<p class="text-foreground/50 text-sm">no members yet</p>
					</div>
				{/if}
			</section>
		{/if}
	</div>
</div>
