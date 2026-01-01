<script lang="ts">
	import ArrowUpTray from '$lib/components/icons/ArrowUpTray.svelte'
	import Bolt from '$lib/components/icons/Bolt.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'

	const chrome = useSystemChrome()

	type IconComponent = typeof Calendar

	interface NotificationItem {
		id: string
		title: string
		body: string
		icon: IconComponent
	}

	const notifications: NotificationItem[] = [
		{
			id: 'upload',
			title: 'upload',
			body: '3 files added to workspace',
			icon: ArrowUpTray,
		},
		{
			id: 'reminder',
			title: 'reminder',
			body: 'standup in 12 minutes',
			icon: Calendar,
		},
		{
			id: 'messages',
			title: 'messages',
			body: 'new thread: product ideas',
			icon: ChatBubbles,
		},
		{
			id: 'automation',
			title: 'automation',
			body: 'night mode scheduled',
			icon: Bolt,
		},
	]
</script>

<aside class="relative h-full w-full" aria-hidden={!chrome.isDockOpen}>
	<div class="flex h-full flex-col gap-4">
		<section
			data-dock-panel
			class="liquid-glass rounded-container px-5 py-4 shadow-[0_24px_48px_rgba(12,10,30,0.45)]"
			aria-label="notifications"
		>
			<span class="liquid-glass__highlight" aria-hidden="true"></span>
			<div class="liquid-glass__content">
				<div class="mb-2 text-xs font-semibold tracking-wide text-white/60">
					notifications
				</div>
				<div class="flex flex-col gap-2">
					{#each notifications as item (item.id)}
						{@const Icon = item.icon}
						<div
							class="flex items-start gap-3 rounded-2xl bg-white/5 px-3 py-3 text-left transition-all duration-150 hover:bg-white/8"
						>
							<div
								class="flex h-9 w-9 items-center justify-center rounded-2xl bg-white/8 text-white/85"
							>
								<Icon className="h-5 w-5" />
							</div>
							<div class="min-w-0">
								<div class="text-[0.8125rem] font-semibold text-white/85">
									{item.title}
								</div>
								<div class="truncate text-[0.8125rem] text-white/55">
									{item.body}
								</div>
							</div>
						</div>
					{/each}
				</div>
			</div>
		</section>

		<div class="flex-1"></div>

		<section
			data-dock-panel
			class="liquid-glass rounded-container px-5 py-4 shadow-[0_24px_48px_rgba(12,10,30,0.45)]"
			aria-label="control center"
		>
			<span class="liquid-glass__highlight" aria-hidden="true"></span>
			<div class="liquid-glass__content">
				<div class="mb-3 text-xs font-semibold tracking-wide text-white/60">
					control center
				</div>

				<div class="grid grid-cols-2 gap-2">
					<button
						class="rounded-2xl border-none bg-white/5 px-3 py-3 text-left text-sm text-white/80 transition-all duration-150 hover:bg-white/8 active:scale-[0.99]"
						type="button"
					>
						wifi
					</button>
					<button
						class="rounded-2xl border-none bg-white/5 px-3 py-3 text-left text-sm text-white/80 transition-all duration-150 hover:bg-white/8 active:scale-[0.99]"
						type="button"
					>
						bluetooth
					</button>
					<button
						class="rounded-2xl border-none bg-white/5 px-3 py-3 text-left text-sm text-white/80 transition-all duration-150 hover:bg-white/8 active:scale-[0.99]"
						type="button"
					>
						focus
					</button>
					<button
						class="rounded-2xl border-none bg-white/5 px-3 py-3 text-left text-sm text-white/80 transition-all duration-150 hover:bg-white/8 active:scale-[0.99]"
						type="button"
					>
						dark mode
					</button>
				</div>
			</div>
		</section>
	</div>
</aside>
