<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type { Component, Snippet } from 'svelte'

	interface Props {
		icon: Component
		label: string
		description: string
		children: Snippet
	}

	let { icon, label, description, children }: Props = $props()
	const Icon = $derived(icon)

	const chrome = useSystemChrome()

	const handleBack = async () => {
		await goto(resolve('/settings'), { keepFocus: true, noScroll: true })
	}

	$effect(() => {
		if (device.isMobile) {
			chrome.setContextActions(mobileBackAction)
			return () => chrome.setContextActions(null)
		}
	})
</script>

{#snippet mobileBackAction()}
	<button
		type="button"
		class="rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
		onclick={handleBack}
		aria-label="back to settings"
	>
		<ChevronLeft strokeWidth="2" />
	</button>
{/snippet}

<div class="min-h-0 w-full flex-1">
	<div class="mx-auto max-w-2xl py-6">
		<header
			class="flex items-center gap-4"
			style="margin-bottom: var(--spacing-header-content);"
		>
			<div class="rounded-container flex h-12 w-12 items-center justify-center bg-white/10">
				<Icon variant="solid" class="h-6 w-6 text-white/80" />
			</div>
			<div class="min-w-0">
				<div class="text-2xl font-semibold text-white/90">{label}</div>
				<div class="mt-1 text-sm text-white/60">{description}</div>
			</div>
		</header>

		{@render children()}
	</div>
</div>
