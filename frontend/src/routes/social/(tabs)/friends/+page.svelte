<script lang="ts">
	import PageTitle from '$lib/components/common/PageTitle.svelte'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import UserPlus from '$lib/components/icons/UserPlusSolid.svelte'
	import Users from '$lib/components/icons/Users.svelte'
	import { modals } from '$lib/stores/modals.svelte'
</script>

<div class="flex flex-1 flex-col gap-6 py-4">
	<div
		class="flex items-center justify-between"
		style="view-transition-name: social-page-header;"
	>
		<PageTitle icon={Users} label="friends" />
		<LiquidGlass class="rounded-full" style="view-transition-name: social-action-btn;">
			<button
				class="interactive flex items-center gap-1.5 rounded-full border-none bg-transparent px-4 py-2 text-sm font-medium text-white/80 hover:text-white"
				onclick={() => modals.open('add-friends')}
			>
				<UserPlus class="h-4 w-4" />
				<span>add friend</span>
			</button>
		</LiquidGlass>
	</div>

	<div
		class="flex flex-1 flex-col items-center justify-center gap-5"
		style="view-transition-name: social-empty-state;"
	>
		<div
			class="flex h-20 w-20 items-center justify-center rounded-full bg-(--accent-primary)/10"
		>
			<Users class="h-10 w-10 text-(--accent-primary)" />
		</div>
		<div class="flex flex-col items-center gap-2 text-center">
			<p class="text-base font-medium text-white/80">no friends yet</p>
			<p class="max-w-xs text-sm text-white/50">
				add friends to share notes, start conversations, and collaborate together.
			</p>
		</div>
	</div>
</div>
