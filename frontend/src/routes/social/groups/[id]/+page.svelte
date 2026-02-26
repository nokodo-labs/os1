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
		class="rounded-pill flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
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
				<div class="h-8 w-48 animate-pulse rounded-full bg-white/5"></div>
				<div class="h-4 w-72 animate-pulse rounded-full bg-white/5"></div>
			</div>
		{:else if !group}
			<div class="rounded-2xl bg-white/5 p-6 text-center">
				<p class="text-sm text-white/50">group not found</p>
			</div>
		{:else}
			<div class="mb-8 flex items-start gap-4 py-2">
				<div
					class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-(--accent-primary)/15"
				>
					<UserGroup class="h-7 w-7 text-(--accent-primary)" variant="solid" />
				</div>
				<div class="flex flex-col gap-1">
					<h1 class="text-xl font-bold text-white">{group.name}</h1>
					{#if group.description}
						<p class="text-sm text-white/60">{group.description}</p>
					{/if}
					<div class="mt-1 flex items-center gap-2 text-xs text-white/45">
						<span>{group.memberships?.length ?? 0} members</span>
						<span class="text-white/20">-</span>
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
				<h2 class="text-sm font-semibold text-white/60">members</h2>

				{#if group.memberships && group.memberships.length > 0}
					<div class="flex flex-col gap-1">
						{#each group.memberships as member (member.id)}
							<button
								class="interactive-subtle flex w-full items-center gap-3 rounded-full p-3 text-left hover:bg-white/5"
								onclick={() => goto(resolve(`/social/users/${member.user_id}`))}
							>
								<div
									class="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-xs font-semibold text-white/80"
								>
									{member.user_id.slice(0, 2).toUpperCase()}
								</div>
								<div class="flex min-w-0 flex-col">
									<span class="truncate text-sm text-white">
										{member.user_id}
									</span>
									<span class="text-xs text-white/45">{member.role}</span>
								</div>
							</button>
						{/each}
					</div>
				{:else}
					<div class="rounded-2xl bg-white/5 py-8 text-center">
						<p class="text-sm text-white/50">no members yet</p>
					</div>
				{/if}
			</section>
		{/if}
	</div>
</div>
