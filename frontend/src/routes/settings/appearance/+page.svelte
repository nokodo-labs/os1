<script lang="ts">
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import Bars3BottomLeft from '$lib/components/icons/Bars3BottomLeft.svelte'
	import ChatBubbleAngular from '$lib/components/icons/ChatBubbleAngular.svelte'
	import ChatBubbleOval from '$lib/components/icons/ChatBubbleOval.svelte'
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
	import CheckDouble from '$lib/components/icons/CheckDouble.svelte'
	import Eye from '$lib/components/icons/Eye.svelte'
	import Minus from '$lib/components/icons/Minus.svelte'
	import Moon from '$lib/components/icons/Moon.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import Sun from '$lib/components/icons/Sun.svelte'
	import Union from '$lib/components/icons/Union.svelte'
	import { RadioGroup, Switch } from '$lib/components/primitives'
	import { appearanceFields } from '$lib/components/settings/fields/appearance'
	import PreferenceScopeToggle from '$lib/components/settings/PreferenceScopeToggle.svelte'
	import SettingsField from '$lib/components/settings/SettingsField.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { accentColors, selectableAccentColors } from '$lib/contexts/themeContext.svelte'
	import { background, isAnimatedBackground } from '$lib/stores/background.svelte'
	import { readReceiptStyle, type ReadReceiptStyle } from '$lib/stores/readReceiptStyle.svelte'
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

	// only wallpapers the API can store: `BackgroundType` here is the generated
	// preferences enum, so a new light/dark sibling appears here once it is added
	// to `backend/api/schemas/preferences.py`. the rest live in /debug/backgrounds.
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

	// tail styles are shapes, not brands: the angular bubble is whatsapp's
	// tight-cornered tail, the oval one is imessage's curl. `Minus` is the
	// shared "nothing applied" glyph for both chat pickers.
	const bubbleTailOptions = [
		{ value: 'none', label: 'none', icon: Minus },
		{ value: 'whatsapp', label: 'whatsapp', icon: ChatBubbleAngular },
		{ value: 'imessage', label: 'imessage', icon: ChatBubbleOval },
	] as const

	const bubbleAnimationOptions = [
		{ value: 'morph', label: 'morph', icon: Union },
		{ value: 'flyup', label: 'fly up', icon: ArrowUp },
		{ value: 'none', label: 'none', icon: Minus },
	] as const

	const readReceiptOptions = [
		{ value: 'ticks', label: 'ticks', icon: CheckDouble },
		{ value: 'text', label: 'text', icon: Bars3BottomLeft },
	] as const

	// this device may not be able to animate at all - then only static is on offer
	const allowsAnimated = $derived(background.allowsAnimated)
	const offeredBackgrounds = $derived(
		allowsAnimated ? backgrounds : backgrounds.filter((bg) => !isAnimatedBackground(bg.value))
	)

	// reactive getters from the typed store
	const selectedBackground = $derived.by((): BackgroundType => {
		const bg = preferences.data.appearance.background
		// background can be disabled via the admin debug toggle. keep the picker usable.
		const selected = bg === 'none' || bg === null ? 'lightrays' : bg
		// show what actually renders, not a stored pick this device cannot run
		return allowsAnimated ? selected : 'static'
	})

	const selectedMode = $derived(preferences.data.appearance.themeMode ?? 'auto')
	const selectedAccent = $derived(preferences.data.appearance.accent)
	const autoAccentColors = $derived(preferences.data.appearance.autoAccentColors ?? true)
	const autoBackground = $derived(preferences.data.appearance.autoBackground ?? true)
	const staticColor = $derived(background.userStaticColor)
	const selectedBubbleTailStyle = $derived(
		preferences.data.appearance.bubbleTailStyle ?? 'imessage'
	)
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

	// local-only until the synced field ships (B28): no scope toggle to offer yet
	const selectedReadReceiptStyle = $derived(readReceiptStyle.style)

	function setReadReceiptStyle(style: string): void {
		readReceiptStyle.set(style as ReadReceiptStyle)
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
		<SettingsField field={appearanceFields.theme} controlLayout="wrap">
			{#snippet control()}
				<PreferenceScopeToggle scope={themeScope} onchange={setThemeScope} />
			{/snippet}
			<RadioGroup
				options={themeModeOptions}
				value={selectedMode}
				onchange={setThemeMode}
				class="mt-4"
			/>
		</SettingsField>

		<SettingsField field={appearanceFields.autoAccentColors}>
			{#snippet control(labelId)}
				<Switch
					size="md"
					checked={autoAccentColors}
					onchange={setAutoAccentColors}
					ariaLabelledbyId={labelId}
				/>
			{/snippet}

			{#if !autoAccentColors}
				<div
					class="border-foreground/15 mt-5 border-t pt-5"
					transition:slide={{ duration: 200 }}
				>
					<SettingsField field={appearanceFields.accentColor} surface="plain" size="sm">
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
					</SettingsField>
				</div>
			{/if}
		</SettingsField>

		<SettingsField field={appearanceFields.wallpaper} controlLayout="wrap">
			{#snippet control()}
				<PreferenceScopeToggle scope={wallpaperScope} onchange={setWallpaperScope} />
			{/snippet}

			<SettingsField
				field={appearanceFields.autoWallpaper}
				surface="plain"
				size="row"
				class="mt-5"
			>
				{#snippet control(labelId)}
					<Switch
						size="md"
						checked={autoBackground}
						onchange={setAutoBackground}
						ariaLabelledbyId={labelId}
					/>
				{/snippet}
			</SettingsField>

			{#if !autoBackground}
				<div
					class="border-foreground/15 mt-5 border-t pt-5"
					transition:slide={{ duration: 200 }}
				>
					<SettingsField
						field={appearanceFields.chooseWallpaper}
						surface="plain"
						size="sm"
						description={allowsAnimated
							? appearanceFields.chooseWallpaper.description
							: 'animated wallpapers are off on this device'}
					>
						<div class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
							{#each offeredBackgrounds as bg (bg.value)}
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
								<label
									class="text-foreground/60 text-sm font-medium"
									for="static-color">static color</label
								>
								<input
									id="static-color"
									type="color"
									value={staticColor}
									oninput={(e) => setStaticColor(e.currentTarget.value)}
									class="border-foreground/20 h-8 w-10 cursor-pointer rounded border bg-transparent"
								/>
								<span class="text-foreground/40 font-mono text-xs"
									>{staticColor}</span
								>
							</div>
						{/if}
					</SettingsField>
				</div>
			{/if}
		</SettingsField>

		<SettingsField field={appearanceFields.chat}>
			{#snippet leading()}
				<ChatBubbles class="text-foreground/60 h-5 w-5" />
			{/snippet}

			<div class="mt-4">
				<SettingsField
					field={appearanceFields.bubbleTails}
					surface="plain"
					size="sm"
					controlLayout="wrap"
				>
					{#snippet control()}
						<PreferenceScopeToggle
							scope={bubbleTailScope}
							onchange={setBubbleTailScope}
						/>
					{/snippet}
					<RadioGroup
						options={bubbleTailOptions}
						value={selectedBubbleTailStyle}
						onchange={setBubbleTailStyle}
						class="mt-4"
					/>
				</SettingsField>
			</div>

			<div class="border-foreground/15 mt-5 border-t pt-5">
				<SettingsField
					field={appearanceFields.bubbleAnimation}
					surface="plain"
					size="sm"
					controlLayout="wrap"
				>
					{#snippet control()}
						<PreferenceScopeToggle
							scope={bubbleAnimationScope}
							onchange={setBubbleAnimationScope}
						/>
					{/snippet}
					<RadioGroup
						options={bubbleAnimationOptions}
						value={selectedBubbleAnimation}
						onchange={setBubbleAnimation}
						class="mt-4"
					/>
				</SettingsField>
			</div>

			<div class="border-foreground/15 mt-5 border-t pt-5">
				<SettingsField
					field={appearanceFields.readReceipts}
					surface="plain"
					size="sm"
					controlLayout="wrap"
				>
					<RadioGroup
						options={readReceiptOptions}
						value={selectedReadReceiptStyle}
						onchange={setReadReceiptStyle}
						class="mt-4"
					/>
				</SettingsField>
			</div>
		</SettingsField>
	</div>
</SettingsSectionLayout>
