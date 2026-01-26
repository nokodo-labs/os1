<script lang="ts">
	import { accentColors } from '$lib/contexts/themeContext.svelte'
	import {
		preferences,
		type AccentColor,
		type BackgroundType,
		type ThemeMode,
	} from '$lib/stores/preferences.svelte'

	const themeModes: { value: ThemeMode; label: string; description: string }[] = [
		{ value: 'light', label: 'light', description: 'always use light mode' },
		{ value: 'dark', label: 'dark', description: 'always use dark mode' },
		{ value: 'system', label: 'auto', description: 'follow system preference' },
	]

	const backgrounds: { value: BackgroundType; label: string }[] = [
		{ value: 'galaxy', label: 'galaxy' },
		{ value: 'darkveil', label: 'dark veil' },
		{ value: 'lightbends', label: 'light bends' },
		{ value: 'lightrays', label: 'light rays' },
		{ value: 'silk', label: 'silk' },
		{ value: 'static', label: 'static color' },
	]

	// reactive getters from the typed store
	const selectedBackground = $derived.by((): BackgroundType => {
		const bg = preferences.background
		// background can be disabled via the admin debug toggle. keep the picker usable.
		return bg === 'none' ? 'darkveil' : bg
	})

	const selectedMode = $derived(preferences.themeMode)
	const selectedAccent = $derived(preferences.accent)

	function setThemeMode(next: ThemeMode): void {
		void preferences.setAppearance({ themeMode: next })
	}

	function setAccent(next: AccentColor): void {
		void preferences.setAppearance({ accent: next })
	}

	function setBackground(bg: BackgroundType): void {
		void preferences.setAppearance({ background: bg })
	}
</script>

<div class="space-y-4">
	<div class="rounded-box bg-white/5 p-5">
		<div class="text-sm font-semibold text-white/85">theme</div>
		<div class="mt-1 text-sm text-white/55">
			choose between light, dark, or automatic theme based on system settings.
		</div>
		<div class="mt-4 flex gap-2">
			{#each themeModes as mode (mode.value)}
				<button
					type="button"
					onclick={() => setThemeMode(mode.value)}
					class="rounded-pill flex-1 border px-4 py-2.5 text-sm font-medium transition-all duration-200 {selectedMode ===
					mode.value
						? 'border-white/20 bg-white/12 text-white shadow-[inset_0_2px_8px_rgba(255,255,255,0.08)]'
						: 'border-transparent bg-white/5 text-white/60 hover:border-white/10 hover:bg-white/8 hover:text-white/80'}"
				>
					{mode.label}
				</button>
			{/each}
		</div>
	</div>

	<div class="rounded-box bg-white/5 p-5">
		<div class="text-sm font-semibold text-white/85">accent color</div>
		<div class="mt-1 text-sm text-white/55">
			customize the accent color used for highlights and selection states.
		</div>
		<div class="mt-4 flex flex-wrap gap-3">
			{#each Object.keys(accentColors) as color (color)}
				{@const colorKey = color as AccentColor}
				{@const isSelected = selectedAccent === colorKey}
				<button
					type="button"
					onclick={() => setAccent(colorKey)}
					class="group rounded-pill flex items-center gap-2.5 border px-3 py-2 transition-all duration-200 {isSelected
						? 'border-white/20 bg-white/12 shadow-[inset_0_2px_8px_rgba(255,255,255,0.08)]'
						: 'border-transparent bg-white/5 hover:border-white/10 hover:bg-white/8'}"
				>
					<span
						class="h-4 w-4 rounded-full ring-2 transition-all {isSelected
							? 'ring-white/40 ring-offset-1 ring-offset-black/20'
							: 'ring-white/10 group-hover:ring-white/20'}"
						style="background-color: {accentColors[colorKey].primary}"
					></span>
					<span
						class="text-sm font-medium {isSelected
							? 'text-white'
							: 'text-white/60 group-hover:text-white/80'}">{color}</span
					>
				</button>
			{/each}
		</div>
	</div>

	<div class="rounded-box bg-white/5 p-5">
		<div class="text-sm font-semibold text-white/85">wallpaper</div>
		<div class="mt-1 text-sm text-white/55">select a dynamic background for the app.</div>
		<div class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
			{#each backgrounds as bg (bg.value)}
				{@const isSelected = selectedBackground === bg.value}
				<button
					type="button"
					onclick={() => setBackground(bg.value)}
					class={`rounded-pill group flex items-center justify-between border px-3 py-2.5 text-left text-sm transition-all duration-200 ${
						isSelected
							? 'border-white/20 bg-white/12 font-medium text-white shadow-[inset_0_2px_8px_rgba(255,255,255,0.08)]'
							: 'border-transparent bg-white/5 text-white/60 hover:border-white/10 hover:bg-white/8 hover:text-white/80'
					}`}
				>
					<span>{bg.label}</span>
					{#if isSelected}
						<span
							class="h-1.5 w-1.5 rounded-full"
							style="background-color: var(--accent-primary)"
						></span>
					{/if}
				</button>
			{/each}
		</div>
	</div>
</div>
