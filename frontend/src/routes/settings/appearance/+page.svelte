<script lang="ts">
	import Eye from '$lib/components/icons/Eye.svelte'
	import Moon from '$lib/components/icons/Moon.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import Sun from '$lib/components/icons/Sun.svelte'
	import { RadioGroup, Switch } from '$lib/components/primitives'
	import PreferenceScopeToggle from '$lib/components/settings/PreferenceScopeToggle.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { accentColors, selectableAccentColors } from '$lib/contexts/themeContext.svelte'
	import { background } from '$lib/stores/background.svelte'
	import {
		preferences,
		type AccentColor,
		type BackgroundType,
		type BubbleAnimation,
		type BubbleTailStyle,
		type ClientPreferenceScope,
		type ThemeMode,
	} from '$lib/stores/preferences.svelte'
	import { slide } from 'svelte/transition'

	const themeModeOptions = [
		{ value: 'auto', label: 'auto', icon: Sparkles },
		{ value: 'light', label: 'light', icon: Sun },
		{ value: 'dark', label: 'dark', icon: Moon },
	] as const

	const backgrounds: { value: BackgroundType; label: string }[] = [
		{ value: 'galaxy', label: 'galaxy' },
		{ value: 'darkveil', label: 'dark veil' },
		{ value: 'lightbends', label: 'light bends' },
		{ value: 'lightrays', label: 'light rays' },
		{ value: 'silk', label: 'silk' },
		{ value: 'fog', label: 'fog' },
		{ value: 'clouds', label: 'clouds' },
		{ value: 'clouds-dark', label: 'clouds dark' },
		{ value: 'clouds2', label: 'clouds 2' },
		{ value: 'clouds2-dark', label: 'clouds 2 dark' },
		{ value: 'grainient', label: 'grainient' },
		{ value: 'iridescence', label: 'iridescence' },
		{ value: 'static', label: 'static color' },
	]

	const bubbleTailOptions = [
		{ value: 'none', label: 'none' },
		{ value: 'whatsapp', label: 'whatsapp' },
		{ value: 'imessage', label: 'imessage' },
	] as const

	const bubbleAnimationOptions = [
		{ value: 'morph', label: 'morph' },
		{ value: 'flyup', label: 'fly up' },
		{ value: 'none', label: 'none' },
	] as const

	// reactive getters from the typed store
	const selectedBackground = $derived.by((): BackgroundType => {
		const bg = preferences.data.appearance.background
		// background can be disabled via the admin debug toggle. keep the picker usable.
		return bg === 'none' || bg === null ? 'lightrays' : bg
	})

	const selectedMode = $derived(preferences.data.appearance.themeMode ?? 'auto')
	const selectedAccent = $derived(preferences.data.appearance.accent)
	const autoAccentColors = $derived(preferences.data.appearance.autoAccentColors ?? true)
	const autoBackground = $derived(preferences.data.appearance.autoBackground ?? true)
	const staticColor = $derived(background.userStaticColor)
	const selectedBubbleTailStyle = $derived(preferences.data.appearance.bubbleTailStyle ?? 'none')
	const selectedBubbleAnimation = $derived(preferences.data.appearance.bubbleAnimation ?? 'morph')
	const themeScope = $derived(preferences.themeScope)
	const wallpaperScope = $derived(preferences.wallpaperScope)
	const bubbleTailScope = $derived(preferences.bubbleTailScope)
	const bubbleAnimationScope = $derived(preferences.bubbleAnimationScope)

	function setThemeMode(next: string): void {
		void preferences.updateThemeMode(next as ThemeMode)
	}

	function setAccent(next: AccentColor): void {
		void preferences.update('appearance', { accent: next })
	}

	function setAutoAccentColors(enabled: boolean): void {
		void preferences.update('appearance', { autoAccentColors: enabled })
	}

	function setBackground(bg: BackgroundType): void {
		background.setBackground(bg)
	}

	function setAutoBackground(enabled: boolean): void {
		background.setAutoBackground(enabled)
	}

	function setStaticColor(color: string): void {
		background.setStaticColor(color)
	}

	function setBubbleTailStyle(style: string): void {
		void preferences.updateBubbleTailStyle(style as BubbleTailStyle)
	}

	function setBubbleAnimation(mode: string): void {
		void preferences.updateBubbleAnimation(mode as BubbleAnimation)
	}

	function setThemeScope(scope: ClientPreferenceScope): void {
		void preferences.setThemeScope(scope)
	}

	function setWallpaperScope(scope: ClientPreferenceScope): void {
		void preferences.setWallpaperScope(scope)
	}

	function setBubbleTailScope(scope: ClientPreferenceScope): void {
		void preferences.setBubbleTailScope(scope)
	}

	function setBubbleAnimationScope(scope: ClientPreferenceScope): void {
		void preferences.setBubbleAnimationScope(scope)
	}
</script>

<SettingsSectionLayout
	icon={Eye}
	label="appearance"
	description="customize theme, colors, and visual preferences"
>
	<div class="space-y-4">
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
				<div>
					<div class="text-foreground text-sm font-semibold">theme</div>
					<div class="text-foreground/50 mt-1 text-sm">
						choose light, dark, or auto which matches the theme to your wallpaper
					</div>
				</div>
				<PreferenceScopeToggle scope={themeScope} onchange={setThemeScope} />
			</div>
			<RadioGroup
				options={themeModeOptions}
				value={selectedMode}
				onchange={setThemeMode}
				class="mt-4"
			/>
		</div>

		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="flex items-center justify-between">
				<div>
					<div class="text-foreground text-sm font-semibold">auto accent colors</div>
					<div class="text-foreground/50 mt-1 text-sm">
						accent colors change automatically based on context
					</div>
				</div>
				<Switch size="md" checked={autoAccentColors} onchange={setAutoAccentColors} />
			</div>

			{#if !autoAccentColors}
				<div
					class="border-foreground/15 mt-5 border-t pt-5"
					transition:slide={{ duration: 200 }}
				>
					<div class="text-foreground text-sm font-semibold">accent color</div>
					<div class="text-foreground/50 mt-1 text-sm">
						customize the accent color used for highlights and selection states
					</div>
					<div class="mt-4 flex flex-wrap gap-3">
						{#each selectableAccentColors as colorKey (colorKey)}
							{@const isSelected = selectedAccent === colorKey}
							<button
								type="button"
								onclick={() => setAccent(colorKey)}
								class="group rounded-pill flex cursor-pointer items-center gap-2.5 border px-3 py-2 transition-all duration-200
									{isSelected
									? 'border-foreground/30 bg-foreground/15'
									: 'border-foreground/10 bg-foreground/5 hover:border-foreground/20 hover:bg-foreground/10'}"
							>
								<!-- radio dot indicator -->
								<span
									class="flex h-4 w-4 items-center justify-center rounded-full border-2 transition-all
										{isSelected ? 'border-foreground' : 'border-foreground/40'}"
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
										? 'text-foreground'
										: 'text-foreground/60 group-hover:text-foreground'}"
									>{colorKey}</span
								>
							</button>
						{/each}
					</div>
				</div>
			{/if}
		</div>

		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
				<div>
					<div class="text-foreground text-sm font-semibold">wallpaper</div>
					<div class="text-foreground/50 mt-1 text-sm">
						choose the app background for all devices or only this one
					</div>
				</div>
				<PreferenceScopeToggle scope={wallpaperScope} onchange={setWallpaperScope} />
			</div>

			<div class="mt-5 flex items-center justify-between gap-4">
				<div>
					<div class="text-foreground/75 text-sm font-medium">auto wallpaper</div>
					<div class="text-foreground/45 mt-1 text-xs">
						wallpaper changes automatically based on context
					</div>
				</div>
				<Switch size="md" checked={autoBackground} onchange={setAutoBackground} />
			</div>

			{#if !autoBackground}
				<div
					class="border-foreground/15 mt-5 border-t pt-5"
					transition:slide={{ duration: 200 }}
				>
					<div class="text-foreground text-sm font-semibold">choose wallpaper</div>
					<div class="text-foreground/50 mt-1 text-sm">
						select a dynamic background for the app
					</div>
					<div class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
						{#each backgrounds as bg (bg.value)}
							{@const isSelected = selectedBackground === bg.value}
							<button
								type="button"
								onclick={() => setBackground(bg.value)}
								class="rounded-pill group flex cursor-pointer items-center gap-2.5 border px-3 py-2.5 text-left text-sm transition-all duration-200
									{isSelected
									? 'border-foreground/30 bg-foreground/15'
									: 'border-foreground/10 bg-foreground/5 hover:border-foreground/20 hover:bg-foreground/10'}"
							>
								<!-- radio dot indicator -->
								<span
									class="flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 transition-all
										{isSelected ? 'border-foreground' : 'border-foreground/40'}"
								>
									{#if isSelected}
										<span class="bg-foreground h-2 w-2 rounded-full"></span>
									{/if}
								</span>
								<span
									class="font-medium {isSelected
										? 'text-foreground'
										: 'text-foreground/60 group-hover:text-foreground'}"
									>{bg.label}</span
								>
							</button>
						{/each}
					</div>

					{#if selectedBackground === 'static'}
						<div
							class="border-foreground/15 mt-4 flex items-center gap-3 border-t pt-4"
							transition:slide={{ duration: 200 }}
						>
							<label class="text-foreground/60 text-sm font-medium" for="static-color"
								>static color</label
							>
							<input
								id="static-color"
								type="color"
								value={staticColor}
								oninput={(e) => setStaticColor(e.currentTarget.value)}
								class="border-foreground/20 h-8 w-10 cursor-pointer rounded border bg-transparent"
							/>
							<span class="text-foreground/40 font-mono text-xs">{staticColor}</span>
						</div>
					{/if}
				</div>
			{/if}
		</div>

		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
				<div>
					<div class="text-foreground text-sm font-semibold">chat bubble tails</div>
					<div class="text-foreground/50 mt-1 text-sm">
						add decorative tails to chat message bubbles, similar to popular messaging
						apps
					</div>
				</div>
				<PreferenceScopeToggle scope={bubbleTailScope} onchange={setBubbleTailScope} />
			</div>
			<RadioGroup
				options={bubbleTailOptions}
				value={selectedBubbleTailStyle}
				onchange={setBubbleTailStyle}
				class="mt-4"
			/>
		</div>

		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
				<div>
					<div class="text-foreground text-sm font-semibold">bubble animation</div>
					<div class="text-foreground/50 mt-1 text-sm">
						how your outgoing message animates into the chat thread
					</div>
				</div>
				<PreferenceScopeToggle
					scope={bubbleAnimationScope}
					onchange={setBubbleAnimationScope}
				/>
			</div>
			<RadioGroup
				options={bubbleAnimationOptions}
				value={selectedBubbleAnimation}
				onchange={setBubbleAnimation}
				class="mt-4"
			/>
		</div>
	</div>
</SettingsSectionLayout>
