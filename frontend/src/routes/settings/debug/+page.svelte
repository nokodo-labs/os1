<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import CommandLine from '$lib/components/icons/CommandLine.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { useDebugUi } from '$lib/contexts/debugUiContext.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import { session } from '$lib/stores/session.svelte'

	const chrome = useSystemChrome()
	const debugUi = useDebugUi()

	const streamdownAnimationTypes = ['fade', 'blur', 'slideUp', 'slideDown'] as const
	const streamdownTokenizeModes = ['word', 'char'] as const

	const isAdmin = $derived(Boolean(session.currentUser?.is_superuser))
	const isBackgroundDisabled = $derived(preferences.data.appearance.background === 'none')

	const handleBackToSettings = async () => {
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
		class="rounded-pill flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
		onclick={handleBackToSettings}
		aria-label="back to settings"
	>
		<ChevronLeft class="h-5 w-5" strokeWidth="2" />
	</button>
{/snippet}

<SettingsSectionLayout
	icon={CommandLine}
	label="debug"
	description="debug-only UI toggles and diagnostics"
>
	{#if !isAdmin}
		<div class="rounded-box border border-red-500/30 bg-red-500/5 p-5">
			<div class="text-sm font-semibold text-red-400">admin only</div>
			<div class="mt-1 text-sm text-white/55">this section is available to superusers.</div>
		</div>
	{:else}
		<div class="space-y-4">
			<div class="rounded-box bg-white/5 p-5">
				<div class="text-sm font-semibold text-white/85">appearance</div>
				<div class="mt-1 text-sm text-white/55">admin-only debug overrides.</div>
				<label class="mt-4 flex items-center justify-between gap-4">
					<span class="text-sm text-white/75">disable background</span>
					<input
						type="checkbox"
						checked={isBackgroundDisabled}
						onchange={(e) => {
							const checked = (e.currentTarget as HTMLInputElement).checked
							void preferences.update('appearance', {
								background: checked ? 'none' : null,
							})
						}}
					/>
				</label>
			</div>

			<div class="rounded-box bg-white/5 p-5">
				<div class="text-sm font-semibold text-white/85">apps grid</div>
				<div class="mt-1 text-sm text-white/55">visual tweaks for the home apps grid.</div>
				<button
					type="button"
					onclick={() => debugUi.toggleAppsGridIconShape()}
					class="rounded-pill mt-4 flex w-full items-center justify-between border border-transparent bg-white/5 px-4 py-2.5 text-sm text-white/80 transition-all duration-200 hover:border-white/10 hover:bg-white/8"
					aria-label="toggle apps grid icon shape"
				>
					<span>icon shape</span>
					<span class="text-white/55">{debugUi.appsGridIconShape}</span>
				</button>
			</div>

			<div class="rounded-box bg-white/5 p-5">
				<div class="text-sm font-semibold text-white/85">markdown streaming</div>
				<div class="mt-1 text-sm text-white/55">
					tune the streamdown animation used while tokens arrive.
				</div>

				<label class="mt-4 flex items-center justify-between gap-4">
					<span class="text-sm text-white/75">enabled</span>
					<input
						type="checkbox"
						checked={debugUi.streamdownAnimation.enabled}
						onchange={(e) => {
							debugUi.setStreamdownAnimation({
								enabled: (e.currentTarget as HTMLInputElement).checked,
							})
						}}
					/>
				</label>

				<div class="mt-4 grid grid-cols-2 gap-2">
					<div class="rounded-pill border border-white/10 bg-white/3 px-3 py-2">
						<div class="text-xs font-semibold text-white/50 uppercase">type</div>
						<div class="mt-2 flex flex-wrap gap-1">
							{#each streamdownAnimationTypes as t (t)}
								<button
									type="button"
									onclick={() => debugUi.setStreamdownAnimation({ type: t })}
									class="rounded-pill px-3 py-1.5 text-xs transition-colors {debugUi
										.streamdownAnimation.type === t
										? 'bg-white/15 text-white'
										: 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/80'}"
								>
									{t}
								</button>
							{/each}
						</div>
					</div>

					<div class="rounded-pill border border-white/10 bg-white/3 px-3 py-2">
						<div class="text-xs font-semibold text-white/50 uppercase">tokenize</div>
						<div class="mt-2 flex flex-wrap gap-1">
							{#each streamdownTokenizeModes as m (m)}
								<button
									type="button"
									onclick={() => debugUi.setStreamdownAnimation({ tokenize: m })}
									class="rounded-pill px-3 py-1.5 text-xs transition-colors {debugUi
										.streamdownAnimation.tokenize === m
										? 'bg-white/15 text-white'
										: 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/80'}"
								>
									{m}
								</button>
							{/each}
						</div>
					</div>
				</div>

				<label class="mt-4 flex items-center justify-between gap-4">
					<span class="text-sm text-white/75">duration (ms)</span>
					<input
						type="number"
						min="50"
						max="3000"
						step="25"
						value={debugUi.streamdownAnimation.duration}
						onchange={(e) => {
							const raw = (e.currentTarget as HTMLInputElement).value
							const parsed = Number.parseInt(raw, 10)
							if (!Number.isFinite(parsed)) return
							debugUi.setStreamdownAnimation({ duration: parsed })
						}}
						class="rounded-pill w-28 border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/85 outline-none"
					/>
				</label>
			</div>
		</div>
	{/if}
</SettingsSectionLayout>
