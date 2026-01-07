<script lang="ts">
	import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
	import { useDebugUi } from '$lib/contexts/debugUiContext.svelte'
	import type { createThemeContext } from '$lib/contexts/themeContext.svelte'
	import {
		accentColors,
		type AccentColor,
		type ThemeMode,
	} from '$lib/contexts/themeContext.svelte'

	type ThemeContext = ReturnType<typeof createThemeContext>

	interface Props {
		theme: ThemeContext
		currentBackground: BackgroundType
		embedded?: boolean
	}

	let { theme, currentBackground = $bindable(), embedded = false }: Props = $props()

	let showDebugMenu = $state(false)

	const debugUi = useDebugUi()

	const streamdownAnimationTypes = ['fade', 'blur', 'slideUp', 'slideDown'] as const
	const streamdownTokenizeModes = ['word', 'char'] as const

	const backgrounds: { value: BackgroundType; label: string }[] = [
		{ value: 'galaxy', label: 'Galaxy' },
		{ value: 'darkveil', label: 'Dark Veil' },
		{ value: 'lightbends', label: 'Light Bends' },
		{ value: 'lightrays', label: 'Light Rays' },
		{ value: 'silk', label: 'Silk' },
		{ value: 'static', label: 'Static Color' },
		{ value: 'none', label: 'None' },
	]
</script>

{#if embedded}
	<div class="w-full rounded-lg bg-black/30 p-3 backdrop-blur-sm">
		<!-- Theme Mode -->
		<div class="mb-2 text-[10px] font-bold text-white/40 uppercase">Theme Mode</div>
		<div class="mb-4 flex gap-1">
			{#each ['light', 'dark', 'system'] as m (m)}
				<button
					onclick={() => theme.setMode(m as ThemeMode)}
					class="flex-1 rounded px-2 py-1.5 text-xs transition-colors {theme.mode === m
						? 'bg-white/20 text-white'
						: 'text-white/60 hover:bg-white/10 hover:text-white'}"
				>
					{m}
				</button>
			{/each}
		</div>

		<!-- Accent Color -->
		<div class="mb-2 text-[10px] font-bold text-white/40 uppercase">Accent Color</div>
		<div class="mb-4 grid grid-cols-3 gap-1">
			{#each Object.keys(accentColors) as color (color)}
				<button
					onclick={() => theme.setAccent(color as AccentColor)}
					class="flex items-center gap-2 rounded px-2 py-1.5 text-xs transition-colors {theme.accent ===
					color
						? 'bg-white/20 text-white'
						: 'text-white/60 hover:bg-white/10 hover:text-white'}"
				>
					<div
						class="h-2 w-2 rounded-full"
						style="background-color: {accentColors[color as AccentColor].primary}"
					></div>
					{color}
				</button>
			{/each}
		</div>

		<!-- Background -->
		<div class="mb-2 text-[10px] font-bold text-white/40 uppercase">Background</div>
		<div class="flex flex-col gap-1">
			{#each backgrounds as bg (bg.value)}
				<button
					onclick={() => {
						currentBackground = bg.value
					}}
					class="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs text-white/80 transition-colors hover:bg-white/10 hover:text-white {currentBackground ===
					bg.value
						? 'bg-white/10 font-medium text-white'
						: ''}"
				>
					{bg.label}
					{#if currentBackground === bg.value}
						<div class="h-1.5 w-1.5 rounded-full bg-white"></div>
					{/if}
				</button>
			{/each}
		</div>

		<!-- Apps Grid -->
		<div class="mt-4 mb-2 text-[10px] font-bold text-white/40 uppercase">Apps Grid</div>
		<button
			type="button"
			onclick={() => debugUi.toggleAppsGridIconShape()}
			class="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs text-white/80 transition-colors hover:bg-white/10 hover:text-white"
			aria-label="toggle apps grid icon shape"
		>
			<span>toggle icon shape</span>
			<span class="text-white/50">{debugUi.appsGridIconShape}</span>
		</button>

		<!-- Markdown Streaming -->
		<div class="mt-4 mb-2 text-[10px] font-bold text-white/40 uppercase">
			Markdown Streaming
		</div>
		<label
			class="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs text-white/80"
		>
			<span>animation</span>
			<input
				type="checkbox"
				checked={debugUi.streamdownAnimation.enabled}
				onchange={(e) =>
					debugUi.setStreamdownAnimation({
						enabled: (e.currentTarget as HTMLInputElement).checked,
					})}
				class="h-3.5 w-3.5 accent-white"
			/>
		</label>

		<div class="grid grid-cols-2 gap-1 px-2 pb-2">
			<label class="flex flex-col gap-1 text-[10px] text-white/50">
				<span>type</span>
				<select
					class="rounded bg-white/10 px-2 py-1 text-xs text-white/90 ring-1 ring-white/10 outline-none hover:bg-white/15"
					value={debugUi.streamdownAnimation.type}
					onchange={(e) =>
						debugUi.setStreamdownAnimation({
							type: (e.currentTarget as HTMLSelectElement)
								.value as (typeof streamdownAnimationTypes)[number],
						})}
				>
					{#each streamdownAnimationTypes as t (t)}
						<option value={t}>{t}</option>
					{/each}
				</select>
			</label>

			<label class="flex flex-col gap-1 text-[10px] text-white/50">
				<span>tokenize</span>
				<select
					class="rounded bg-white/10 px-2 py-1 text-xs text-white/90 ring-1 ring-white/10 outline-none hover:bg-white/15"
					value={debugUi.streamdownAnimation.tokenize}
					onchange={(e) =>
						debugUi.setStreamdownAnimation({
							tokenize: (e.currentTarget as HTMLSelectElement)
								.value as (typeof streamdownTokenizeModes)[number],
						})}
				>
					{#each streamdownTokenizeModes as m (m)}
						<option value={m}>{m}</option>
					{/each}
				</select>
			</label>
		</div>

		<label
			class="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs text-white/80"
		>
			<span>duration</span>
			<input
				type="number"
				min="50"
				max="3000"
				step="50"
				value={debugUi.streamdownAnimation.duration}
				onchange={(e) =>
					debugUi.setStreamdownAnimation({
						duration: Number.parseInt((e.currentTarget as HTMLInputElement).value, 10),
					})}
				class="w-20 rounded bg-white/10 px-2 py-1 text-xs text-white/90 ring-1 ring-white/10 outline-none"
			/>
		</label>
	</div>
{:else}
	<div class="fixed top-4 right-4 z-50">
		<div class="relative">
			<button
				onclick={() => (showDebugMenu = !showDebugMenu)}
				class="flex items-center gap-2 rounded-lg bg-black/50 px-3 py-2 text-xs text-white/80 backdrop-blur-sm transition-colors hover:bg-black/70 hover:text-white"
			>
				<span>Debug Controls</span>
				<span class="ml-1">▼</span>
			</button>

			{#if showDebugMenu}
				<div
					class="absolute top-full right-0 mt-1 w-56 rounded-lg bg-black/90 p-3 shadow-xl backdrop-blur-sm"
				>
					<!-- Theme Mode -->
					<div class="mb-2 text-[10px] font-bold text-white/40 uppercase">Theme Mode</div>
					<div class="mb-4 flex gap-1">
						{#each ['light', 'dark', 'system'] as m (m)}
							<button
								onclick={() => theme.setMode(m as ThemeMode)}
								class="flex-1 rounded px-2 py-1.5 text-xs transition-colors {theme.mode ===
								m
									? 'bg-white/20 text-white'
									: 'text-white/60 hover:bg-white/10 hover:text-white'}"
							>
								{m}
							</button>
						{/each}
					</div>

					<!-- Accent Color -->
					<div class="mb-2 text-[10px] font-bold text-white/40 uppercase">
						Accent Color
					</div>
					<div class="mb-4 grid grid-cols-3 gap-1">
						{#each Object.keys(accentColors) as color (color)}
							<button
								onclick={() => theme.setAccent(color as AccentColor)}
								class="flex items-center gap-2 rounded px-2 py-1.5 text-xs transition-colors {theme.accent ===
								color
									? 'bg-white/20 text-white'
									: 'text-white/60 hover:bg-white/10 hover:text-white'}"
							>
								<div
									class="h-2 w-2 rounded-full"
									style="background-color: {accentColors[color as AccentColor]
										.primary}"
								></div>
								{color}
							</button>
						{/each}
					</div>

					<!-- Background -->
					<div class="mb-2 text-[10px] font-bold text-white/40 uppercase">Background</div>
					<div class="flex flex-col gap-1">
						{#each backgrounds as bg (bg.value)}
							<button
								onclick={() => {
									currentBackground = bg.value
								}}
								class="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs text-white/80 transition-colors hover:bg-white/10 hover:text-white {currentBackground ===
								bg.value
									? 'bg-white/10 font-medium text-white'
									: ''}"
							>
								{bg.label}
								{#if currentBackground === bg.value}
									<div class="h-1.5 w-1.5 rounded-full bg-white"></div>
								{/if}
							</button>
						{/each}
					</div>

					<!-- Apps Grid -->
					<div class="mt-4 mb-2 text-[10px] font-bold text-white/40 uppercase">
						Apps Grid
					</div>
					<button
						type="button"
						onclick={() => debugUi.toggleAppsGridIconShape()}
						class="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs text-white/80 transition-colors hover:bg-white/10 hover:text-white"
						aria-label="toggle apps grid icon shape"
					>
						<span>toggle icon shape</span>
						<span class="text-white/50">{debugUi.appsGridIconShape}</span>
					</button>

					<!-- Markdown Streaming -->
					<div class="mt-4 mb-2 text-[10px] font-bold text-white/40 uppercase">
						Markdown Streaming
					</div>
					<label
						class="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs text-white/80"
					>
						<span>animation</span>
						<input
							type="checkbox"
							checked={debugUi.streamdownAnimation.enabled}
							onchange={(e) =>
								debugUi.setStreamdownAnimation({
									enabled: (e.currentTarget as HTMLInputElement).checked,
								})}
							class="h-3.5 w-3.5 accent-white"
						/>
					</label>

					<div class="grid grid-cols-2 gap-1 px-2 pb-2">
						<label class="flex flex-col gap-1 text-[10px] text-white/50">
							<span>type</span>
							<select
								class="rounded bg-white/10 px-2 py-1 text-xs text-white/90 ring-1 ring-white/10 outline-none hover:bg-white/15"
								value={debugUi.streamdownAnimation.type}
								onchange={(e) =>
									debugUi.setStreamdownAnimation({
										type: (e.currentTarget as HTMLSelectElement)
											.value as (typeof streamdownAnimationTypes)[number],
									})}
							>
								{#each streamdownAnimationTypes as t (t)}
									<option value={t}>{t}</option>
								{/each}
							</select>
						</label>

						<label class="flex flex-col gap-1 text-[10px] text-white/50">
							<span>tokenize</span>
							<select
								class="rounded bg-white/10 px-2 py-1 text-xs text-white/90 ring-1 ring-white/10 outline-none hover:bg-white/15"
								value={debugUi.streamdownAnimation.tokenize}
								onchange={(e) =>
									debugUi.setStreamdownAnimation({
										tokenize: (e.currentTarget as HTMLSelectElement)
											.value as (typeof streamdownTokenizeModes)[number],
									})}
							>
								{#each streamdownTokenizeModes as m (m)}
									<option value={m}>{m}</option>
								{/each}
							</select>
						</label>
					</div>

					<label
						class="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs text-white/80"
					>
						<span>duration</span>
						<input
							type="number"
							min="50"
							max="3000"
							step="50"
							value={debugUi.streamdownAnimation.duration}
							onchange={(e) =>
								debugUi.setStreamdownAnimation({
									duration: Number.parseInt(
										(e.currentTarget as HTMLInputElement).value,
										10
									),
								})}
							class="w-20 rounded bg-white/10 px-2 py-1 text-xs text-white/90 ring-1 ring-white/10 outline-none"
						/>
					</label>
				</div>
			{/if}
		</div>
	</div>
{/if}
