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
		class="rounded-pill hover:text-foreground flex cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97]"
		onclick={handleBack}
		aria-label="back to settings"
	>
		<ChevronLeft strokeWidth="2" />
	</button>
{/snippet}

<div class="settings-section-content min-h-0 w-full flex-1">
	<div class="mx-auto max-w-2xl py-6">
		<header
			class="flex items-center gap-4"
			style="margin-bottom: var(--spacing-header-content);"
		>
			<div
				class="rounded-container bg-foreground/10 flex h-12 w-12 items-center justify-center"
			>
				<Icon variant="solid" class="text-foreground/80 h-6 w-6" />
			</div>
			<div class="min-w-0">
				<div class="text-foreground/90 text-2xl font-semibold">{label}</div>
				<div class="text-foreground/60 mt-1 text-sm">{description}</div>
			</div>
		</header>

		{@render children()}
	</div>
</div>

<style>
	.settings-section-content {
		--radius-container-base: 1.25rem;
	}

	.settings-section-content :global(.rounded-container.liquid-glass > div:first-child:not(.flex)),
	.settings-section-content
		:global(.rounded-container.liquid-glass > div:first-child.flex > div:last-child) {
		font-size: 1rem;
		line-height: 1.5rem;
		font-weight: 650;
	}
</style>
