<script lang="ts">
	import { resolve } from '$app/paths'
	import CommandLine from '$lib/components/icons/CommandLine.svelte'
	import { debugFields } from '$lib/components/settings/fields/debug'
	import SettingsField from '$lib/components/settings/SettingsField.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { useDebugUi } from '$lib/contexts/debugUiContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import { session } from '$lib/stores/session.svelte'

	const debugUi = useDebugUi()

	const streamdownAnimationTypes = ['fade', 'blur', 'slideUp', 'slideDown'] as const
	const streamdownTokenizeModes = ['word', 'char'] as const
	const sendAnimationModes = ['morph', 'flyup', 'none'] as const

	const isAdmin = $derived(Boolean(session.currentUser?.is_superuser))
	const isBackgroundDisabled = $derived(preferences.data.appearance.background === 'none')
</script>

<SettingsSectionLayout
	icon={CommandLine}
	label="debug"
	description="debug-only UI toggles and diagnostics"
>
	{#if !isAdmin}
		<div class="rounded-container border border-red-500/30 bg-red-500/5 p-5">
			<div class="text-sm font-semibold text-red-400">admin only</div>
			<div class="text-foreground/55 mt-1 text-sm">
				this section is available to superusers.
			</div>
		</div>
	{:else}
		<div class="space-y-4">
			<SettingsField field={debugFields.debugApps}>
				<label class="mt-4 flex items-center justify-between gap-4">
					<span class="text-foreground/75 text-sm">enable debug apps</span>
					<input
						type="checkbox"
						checked={preferences.data.debug.enableDebugApps}
						onchange={(e) => {
							const checked = (e.currentTarget as HTMLInputElement).checked
							void preferences.update('debug', {
								enableDebugApps: checked,
							})
						}}
					/>
				</label>
			</SettingsField>

			<SettingsField field={debugFields.appearance}>
				<label class="mt-4 flex items-center justify-between gap-4">
					<span class="text-foreground/75 text-sm">disable background</span>
					<input
						type="checkbox"
						checked={isBackgroundDisabled}
						onchange={(e) => {
							const checked = (e.currentTarget as HTMLInputElement).checked
							void preferences.update('appearance', {
								background: checked ? 'none' : undefined,
							})
						}}
					/>
				</label>
			</SettingsField>

			<SettingsField field={debugFields.debugPages}>
				<div class="mt-4 flex flex-wrap gap-2">
					<a
						href={resolve('/debug')}
						class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/75 hover:border-foreground/20 hover:bg-foreground/8 border px-3 py-2 text-xs transition"
					>
						open debug index
					</a>
				</div>
			</SettingsField>

			<SettingsField field={debugFields.deviceInsights}>
				<div class="text-foreground/75 mt-4 grid gap-3 text-sm sm:grid-cols-2">
					<div class="rounded-pill border-foreground/10 bg-foreground/3 border px-3 py-2">
						<div class="text-foreground/50 text-xs font-semibold uppercase">
							gpu tier
						</div>
						<div class="text-foreground/85 mt-1">{device.gpuTier}</div>
					</div>
					<div class="rounded-pill border-foreground/10 bg-foreground/3 border px-3 py-2">
						<div class="text-foreground/50 text-xs font-semibold uppercase">score</div>
						<div class="text-foreground/85 mt-1">{device.gpuDiagnostics.score}</div>
					</div>
					<div class="rounded-pill border-foreground/10 bg-foreground/3 border px-3 py-2">
						<div class="text-foreground/50 text-xs font-semibold uppercase">cores</div>
						<div class="text-foreground/85 mt-1">{device.gpuDiagnostics.cores}</div>
					</div>
					<div class="rounded-pill border-foreground/10 bg-foreground/3 border px-3 py-2">
						<div class="text-foreground/50 text-xs font-semibold uppercase">memory</div>
						<div class="text-foreground/85 mt-1">
							{device.gpuDiagnostics.memoryGb !== null
								? `${device.gpuDiagnostics.memoryGb} gb`
								: 'unknown'}
						</div>
					</div>
					<div class="rounded-pill border-foreground/10 bg-foreground/3 border px-3 py-2">
						<div class="text-foreground/50 text-xs font-semibold uppercase">webgl</div>
						<div class="text-foreground/85 mt-1">{device.gpuDiagnostics.webgl}</div>
					</div>
					<div class="rounded-pill border-foreground/10 bg-foreground/3 border px-3 py-2">
						<div class="text-foreground/50 text-xs font-semibold uppercase">
							renderer source
						</div>
						<div class="text-foreground/85 mt-1">
							{device.gpuDiagnostics.rendererSource}
						</div>
					</div>
				</div>

				<div
					class="rounded-pill border-foreground/10 bg-foreground/3 mt-4 border px-3 py-2"
				>
					<div class="text-foreground/50 text-xs font-semibold uppercase">renderer</div>
					<div class="text-foreground/85 mt-1 text-sm break-all">
						{device.gpuDiagnostics.renderer ?? 'unknown'}
					</div>
				</div>

				<div class="text-foreground/75 mt-4 grid gap-3 text-sm sm:grid-cols-2">
					<div class="rounded-pill border-foreground/10 bg-foreground/3 border px-3 py-2">
						<div class="text-foreground/50 text-xs font-semibold uppercase">mobile</div>
						<div class="text-foreground/85 mt-1">
							{device.gpuDiagnostics.isMobile ? 'yes' : 'no'}
						</div>
					</div>
					<div class="rounded-pill border-foreground/10 bg-foreground/3 border px-3 py-2">
						<div class="text-foreground/50 text-xs font-semibold uppercase">touch</div>
						<div class="text-foreground/85 mt-1">
							{device.gpuDiagnostics.isTouch ? 'yes' : 'no'}
						</div>
					</div>
					<div class="rounded-pill border-foreground/10 bg-foreground/3 border px-3 py-2">
						<div class="text-foreground/50 text-xs font-semibold uppercase">
							coarse pointer
						</div>
						<div class="text-foreground/85 mt-1">
							{device.gpuDiagnostics.isCoarsePointer ? 'yes' : 'no'}
						</div>
					</div>
					<div class="rounded-pill border-foreground/10 bg-foreground/3 border px-3 py-2">
						<div class="text-foreground/50 text-xs font-semibold uppercase">hover</div>
						<div class="text-foreground/85 mt-1">
							{device.gpuDiagnostics.hasHover ? 'yes' : 'no'}
						</div>
					</div>
				</div>

				{#if device.gpuDiagnostics.notes.length > 0}
					<div class="mt-4">
						<div class="text-foreground/50 text-xs font-semibold uppercase">notes</div>
						<div class="mt-2 flex flex-wrap gap-2">
							{#each device.gpuDiagnostics.notes as note (note)}
								<span
									class="rounded-pill border-foreground/10 bg-foreground/3 text-foreground/75 border px-3 py-1.5 text-xs"
								>
									{note}
								</span>
							{/each}
						</div>
					</div>
				{/if}
			</SettingsField>

			<SettingsField field={debugFields.appsGrid}>
				<button
					type="button"
					onclick={() => debugUi.toggleAppsGridIconShape()}
					class="rounded-pill bg-foreground/5 text-foreground/80 hover:border-foreground/10 hover:bg-foreground/8 mt-4 flex w-full items-center justify-between border border-transparent px-4 py-2.5 text-sm transition-all duration-200"
					aria-label="toggle apps grid icon shape"
				>
					<span>icon shape</span>
					<span class="text-foreground/55">{debugUi.appsGridIconShape}</span>
				</button>
			</SettingsField>

			<SettingsField field={debugFields.markdownStreaming}>
				<label class="mt-4 flex items-center justify-between gap-4">
					<span class="text-foreground/75 text-sm">enabled</span>
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
					<div class="rounded-pill border-foreground/10 bg-foreground/3 border px-3 py-2">
						<div class="text-foreground/50 text-xs font-semibold uppercase">type</div>
						<div class="mt-2 flex flex-wrap gap-1">
							{#each streamdownAnimationTypes as t (t)}
								<button
									type="button"
									onclick={() => debugUi.setStreamdownAnimation({ type: t })}
									class="rounded-pill px-3 py-1.5 text-xs transition-colors {debugUi
										.streamdownAnimation.type === t
										? 'bg-foreground/15 text-foreground'
										: 'bg-foreground/5 text-foreground/60 hover:bg-foreground/10 hover:text-foreground/80'}"
								>
									{t}
								</button>
							{/each}
						</div>
					</div>

					<div class="rounded-pill border-foreground/10 bg-foreground/3 border px-3 py-2">
						<div class="text-foreground/50 text-xs font-semibold uppercase">
							tokenize
						</div>
						<div class="mt-2 flex flex-wrap gap-1">
							{#each streamdownTokenizeModes as m (m)}
								<button
									type="button"
									onclick={() => debugUi.setStreamdownAnimation({ tokenize: m })}
									class="rounded-pill px-3 py-1.5 text-xs transition-colors {debugUi
										.streamdownAnimation.tokenize === m
										? 'bg-foreground/15 text-foreground'
										: 'bg-foreground/5 text-foreground/60 hover:bg-foreground/10 hover:text-foreground/80'}"
								>
									{m}
								</button>
							{/each}
						</div>
					</div>
				</div>

				<label class="mt-4 flex items-center justify-between gap-4">
					<span class="text-foreground/75 text-sm">duration (ms)</span>
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
						class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/85 w-28 border px-3 py-2 text-sm outline-none"
					/>
				</label>
			</SettingsField>

			<SettingsField field={debugFields.chatSendAnimation}>
				<div class="mt-4 flex flex-wrap gap-1">
					{#each sendAnimationModes as m (m)}
						<button
							type="button"
							onclick={() => debugUi.setSendAnimationMode(m)}
							class="rounded-pill px-3 py-1.5 text-xs transition-colors {debugUi.sendAnimationMode ===
							m
								? 'bg-foreground/15 text-foreground'
								: 'bg-foreground/5 text-foreground/60 hover:bg-foreground/10 hover:text-foreground/80'}"
						>
							{m}
						</button>
					{/each}
				</div>
			</SettingsField>
		</div>
	{/if}
</SettingsSectionLayout>
