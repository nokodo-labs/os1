<script lang="ts">
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import Download from '$lib/components/icons/Download.svelte'
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import Wrench from '$lib/components/icons/Wrench.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
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
</script>

<SettingsSectionLayout
	icon={Wrench}
	label="advanced"
	description="data management, imports, and danger zone"
>
	<div class="space-y-4">
		<!-- data export -->
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white">data export</div>
			<div class="mt-1 text-sm text-white/50">download your data in portable formats.</div>
			<div class="mt-4 space-y-2">
				{#each exportActions as action (action.label)}
					{@const Icon = action.icon}
					<button
						type="button"
						disabled
						class="rounded-pill flex w-full items-center gap-3 border border-white/10 bg-white/3 px-4 py-3 text-left text-sm transition-all hover:border-white/15 hover:bg-white/5 disabled:opacity-50"
					>
						<Icon class="h-4.5 w-4.5 shrink-0 text-white/50" />
						<div class="min-w-0 flex-1">
							<div class="font-medium text-white/80">{action.label}</div>
							<div class="text-xs text-white/50">{action.description}</div>
						</div>
						<span
							class="rounded-pill bg-white/5 px-2 py-0.5 text-[0.65rem] text-white/45"
							>soon</span
						>
					</button>
				{/each}
			</div>
		</div>

		<!-- chat management -->
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white">chat management</div>
			<div class="mt-1 text-sm text-white/50">organize or clean up your conversations.</div>
			<div class="mt-4 space-y-2">
				{#each manageActions as action (action.label)}
					{@const Icon = action.icon}
					<button
						type="button"
						disabled
						class="rounded-pill flex w-full items-center gap-3 border px-4 py-3 text-left text-sm transition-all disabled:opacity-50
							{action.variant === 'danger'
							? 'border-red-500/20 bg-red-500/5 hover:border-red-500/30 hover:bg-red-500/10'
							: 'border-white/10 bg-white/3 hover:border-white/15 hover:bg-white/5'}"
					>
						<Icon
							class="h-4.5 w-4.5 shrink-0 {action.variant === 'danger'
								? 'text-red-400/60'
								: 'text-white/50'}"
						/>
						<div class="min-w-0 flex-1">
							<div
								class="font-medium {action.variant === 'danger'
									? 'text-red-400/80'
									: 'text-white/80'}"
							>
								{action.label}
							</div>
							<div class="text-xs text-white/50">{action.description}</div>
						</div>
						<span
							class="rounded-pill bg-white/5 px-2 py-0.5 text-[0.65rem] text-white/45"
							>soon</span
						>
					</button>
				{/each}
			</div>
		</div>

		<!-- open webui import -->
		<div class="rounded-container bg-white/5">
			<button
				type="button"
				class="flex w-full cursor-pointer items-center justify-between border-none bg-transparent p-5 text-left"
				onclick={() => (owuiExpanded = !owuiExpanded)}
			>
				<div>
					<div class="text-sm font-semibold text-white">open webui import</div>
					<div class="mt-1 text-sm text-white/50">
						import data from an open webui instance.
					</div>
				</div>
				<ChevronDown
					class="h-4.5 w-4.5 text-white/50 transition-transform duration-200 {owuiExpanded
						? 'rotate-180'
						: ''}"
				/>
			</button>

			{#if owuiExpanded}
				<div
					class="border-t border-white/14 px-5 pt-4 pb-5"
					transition:slide={{ duration: 200 }}
				>
					<form class="space-y-3" onsubmit={(e) => e.preventDefault()} autocomplete="off">
						<div>
							<label
								class="mb-1.5 block text-xs font-medium text-white/50"
								for="owui-host">host URL</label
							>
							<input
								id="owui-host"
								type="url"
								class="rounded-pill w-full border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white/90 placeholder-white/40 transition-colors outline-none focus:border-white/20 focus:bg-white/8"
								placeholder="https://your-open-webui.example.com"
								bind:value={owuiHost}
							/>
						</div>
						<div>
							<label
								class="mb-1.5 block text-xs font-medium text-white/50"
								for="owui-jwt">JWT token</label
							>
							<input
								id="owui-jwt"
								type="password"
								autocomplete="off"
								class="rounded-pill w-full border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white/90 placeholder-white/40 transition-colors outline-none focus:border-white/20 focus:bg-white/8"
								placeholder="paste your open webui JWT here"
								bind:value={owuiJwt}
							/>
						</div>

						<div class="flex gap-2 pt-1">
							<button
								type="button"
								disabled
								class="rounded-pill flex-1 border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/50 transition-colors disabled:opacity-50"
							>
								import all chats
							</button>
							<button
								type="button"
								disabled
								class="rounded-pill flex-1 border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/50 transition-colors disabled:opacity-50"
							>
								import all memories
							</button>
						</div>
						<p class="text-xs text-white/45">coming soon</p>
					</form>

					<div class="mt-5 border-t border-white/14 pt-4">
						<div class="text-xs font-medium text-white/50">
							more imports coming soon
						</div>
						<div class="mt-2 flex flex-wrap gap-2">
							{#each ['ChatGPT', 'Claude', 'Gemini', 'LibreChat'] as platform (platform)}
								<span
									class="rounded-pill border border-white/14 bg-white/3 px-3 py-1 text-xs text-white/45"
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
				<GarbageBin class="h-4.5 w-4.5 text-red-400/70" />
				<div class="text-sm font-semibold text-red-400">danger zone</div>
			</div>
			<div class="mt-1 text-sm text-white/50">
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
				<p class="mt-2 text-xs text-white/45">
					this will permanently delete your account and all associated data. coming soon.
				</p>
			</div>
		</div>
	</div>
</SettingsSectionLayout>
