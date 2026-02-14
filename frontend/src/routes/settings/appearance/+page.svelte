<script lang="ts">
	import Eye from '$lib/components/icons/Eye.svelte'
	import { RadioGroup, Switch } from '$lib/components/primitives'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { accentColors, selectableAccentColors } from '$lib/contexts/themeContext.svelte'
	import { background } from '$lib/stores/background.svelte'
	import {
		preferences,
		type AccentColor,
		type BackgroundType,
		type BubbleTailStyle,
		type ThemeMode,
	} from '$lib/stores/preferences.svelte'
	import { slide } from 'svelte/transition'

	const themeModeOptions = [
		{ value: 'light', label: 'light' },
		{ value: 'dark', label: 'dark' },
		{ value: 'system', label: 'auto' },
	] as const

	const backgrounds: { value: BackgroundType; label: string }[] = [
		{ value: 'galaxy', label: 'galaxy' },
		{ value: 'darkveil', label: 'dark veil' },
		{ value: 'lightbends', label: 'light bends' },
		{ value: 'lightrays', label: 'light rays' },
		{ value: 'silk', label: 'silk' },
		{ value: 'static', label: 'static color' },
	]

	const bubbleTailOptions = [
		{ value: 'none', label: 'none' },
		{ value: 'whatsapp', label: 'whatsapp' },
		{ value: 'imessage', label: 'imessage' },
	] as const

	// reactive getters from the typed store
	const selectedBackground = $derived.by((): BackgroundType => {
		const bg = preferences.data.appearance.background
		// background can be disabled via the admin debug toggle. keep the picker usable.
		return bg === 'none' || bg === null ? 'lightrays' : bg
	})

	const selectedMode = $derived(preferences.data.appearance.themeMode ?? 'system')
	const selectedAccent = $derived(preferences.data.appearance.accent)
	const autoAccentColors = $derived(preferences.data.appearance.autoAccentColors ?? true)
	const autoBackground = $derived(preferences.data.appearance.autoBackground ?? true)
	const staticColor = $derived(preferences.data.appearance.staticColor ?? '#171717')
	const selectedBubbleTailStyle = $derived(preferences.data.appearance.bubbleTailStyle ?? 'none')

	function setThemeMode(next: string): void {
		void preferences.update('appearance', { themeMode: next as ThemeMode })
	}

	function setAccent(next: AccentColor): void {
		void preferences.update('appearance', { accent: next })
	}

	function setAutoAccentColors(enabled: boolean): void {
		void preferences.update('appearance', { autoAccentColors: enabled })
	}

	function setBackground(bg: BackgroundType): void {
		void preferences.update('appearance', { background: bg })
	}

	function setAutoBackground(enabled: boolean): void {
		background.setAutoBackground(enabled)
	}

	function setStaticColor(color: string): void {
		background.setStaticColor(color)
	}

	function setBubbleTailStyle(style: string): void {
		void preferences.update('appearance', { bubbleTailStyle: style as BubbleTailStyle })
	}
</script>

<SettingsSectionLayout
	icon={Eye}
	label="appearance"
	description="customize theme, colors, and visual preferences"
>
	<div class="space-y-4">
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white">theme</div>
			<div class="mt-1 text-sm text-white/50">
				choose between light, dark, or automatic theme based on system settings.
			</div>
			<RadioGroup
				options={themeModeOptions}
				value={selectedMode}
				onchange={setThemeMode}
				class="mt-4"
			/>
		</div>

		<div class="rounded-container bg-white/5 p-5">
			<div class="flex items-center justify-between">
				<div>
					<div class="text-sm font-semibold text-white">auto accent colors</div>
					<div class="mt-1 text-sm text-white/50">
						accent colors change automatically based on the current page.
					</div>
				</div>
				<Switch size="md" checked={autoAccentColors} onchange={setAutoAccentColors} />
			</div>

			{#if !autoAccentColors}
				<div
					class="mt-5 border-t border-white/10 pt-5"
					transition:slide={{ duration: 200 }}
				>
					<div class="text-sm font-semibold text-white">accent color</div>
					<div class="mt-1 text-sm text-white/50">
						customize the accent color used for highlights and selection states.
					</div>
					<div class="mt-4 flex flex-wrap gap-3">
						{#each selectableAccentColors as colorKey (colorKey)}
							{@const isSelected = selectedAccent === colorKey}
							<button
								type="button"
								onclick={() => setAccent(colorKey)}
								class="group rounded-pill flex cursor-pointer items-center gap-2.5 border px-3 py-2 transition-all duration-200
									{isSelected
									? 'border-white/30 bg-white/15'
									: 'border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/10'}"
							>
								<!-- radio dot indicator -->
								<span
									class="flex h-4 w-4 items-center justify-center rounded-full border-2 transition-all
										{isSelected ? 'border-white' : 'border-white/40'}"
								>
									{#if isSelected}
										<span
											class="h-2 w-2 rounded-full"
											style="background-color: {accentColors[colorKey]
												.primary}"
										></span>
									{/if}
								</span>
								<span
									class="text-sm font-medium {isSelected
										? 'text-white'
										: 'text-white/60 group-hover:text-white'}">{colorKey}</span
								>
							</button>
						{/each}
					</div>
				</div>
			{/if}
		</div>

		<div class="rounded-container bg-white/5 p-5">
			<div class="flex items-center justify-between">
				<div>
					<div class="text-sm font-semibold text-white">auto wallpaper</div>
					<div class="mt-1 text-sm text-white/50">
						wallpaper changes automatically based on the current page.
					</div>
				</div>
				<Switch size="md" checked={autoBackground} onchange={setAutoBackground} />
			</div>

			{#if !autoBackground}
				<div
					class="mt-5 border-t border-white/10 pt-5"
					transition:slide={{ duration: 200 }}
				>
					<div class="text-sm font-semibold text-white">wallpaper</div>
					<div class="mt-1 text-sm text-white/50">
						select a dynamic background for the app.
					</div>
					<div class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
						{#each backgrounds as bg (bg.value)}
							{@const isSelected = selectedBackground === bg.value}
							<button
								type="button"
								onclick={() => setBackground(bg.value)}
								class="rounded-pill group flex cursor-pointer items-center gap-2.5 border px-3 py-2.5 text-left text-sm transition-all duration-200
									{isSelected
									? 'border-white/30 bg-white/15'
									: 'border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/10'}"
							>
								<!-- radio dot indicator -->
								<span
									class="flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 transition-all
										{isSelected ? 'border-white' : 'border-white/40'}"
								>
									{#if isSelected}
										<span class="h-2 w-2 rounded-full bg-white"></span>
									{/if}
								</span>
								<span
									class="font-medium {isSelected
										? 'text-white'
										: 'text-white/60 group-hover:text-white'}">{bg.label}</span
								>
							</button>
						{/each}
					</div>

					{#if selectedBackground === 'static'}
						<div
							class="mt-4 flex items-center gap-3 border-t border-white/10 pt-4"
							transition:slide={{ duration: 200 }}
						>
							<label class="text-sm font-medium text-white/60" for="static-color"
								>static color</label
							>
							<input
								id="static-color"
								type="color"
								value={staticColor}
								oninput={(e) => setStaticColor(e.currentTarget.value)}
								class="h-8 w-10 cursor-pointer rounded border border-white/20 bg-transparent"
							/>
							<span class="font-mono text-xs text-white/40">{staticColor}</span>
						</div>
					{/if}
				</div>
			{/if}
		</div>

		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white">chat bubble tails</div>
			<div class="mt-1 text-sm text-white/50">
				add decorative tails to chat message bubbles, similar to popular messaging apps.
			</div>
			<RadioGroup
				options={bubbleTailOptions}
				value={selectedBubbleTailStyle}
				onchange={setBubbleTailStyle}
				class="mt-4"
			/>
		</div>
	</div>
</SettingsSectionLayout>
