<script lang="ts">
	import { browser } from '$app/environment'
	import { resolve } from '$app/paths'
	import type {
		BackgroundConfig,
		BackgroundType,
	} from '$lib/components/backgrounds/BackgroundManager.svelte'
	import { background } from '$lib/stores/background.svelte'
	import { onDestroy } from 'svelte'

	const STORAGE_SELECTED = 'debug:backgrounds:selected'
	const STORAGE_CONFIG = 'debug:backgrounds:config'

	const backgrounds: BackgroundType[] = [
		'galaxy',
		'darkveil',
		'lightbends',
		'lightrays',
		'silk',
		'fog',
		'clouds',
		'clouds2',
		'static',
		'none',
	]

	const DEFAULT_CONFIG: BackgroundConfig = {
		color: '#171717',
		lightBendsColors: ['#ff0080', '#0080ff', '#00ff80'],
		lightBendsSpeed: 0.2,
		lightBendsWarp: 1,
		raysOrigin: 'top-center',
		raysColor: '#ffffff',
		raysSpeed: 1,
		silkColor: '#7B7481',
		silkSpeed: 5,
		fogHighlightColor: 0xffc300,
		fogMidtoneColor: 0xff1f00,
		fogLowlightColor: 0x2d00ff,
		fogBaseColor: 0x0f091f,
		fogBlurFactor: 0.6,
		fogSpeed: 1,
		fogZoom: 1,
		fogMouseControls: true,
		fogTouchControls: true,
		fogGyroControls: false,
		fogMinHeight: 200,
		fogMinWidth: 200,
		cloudsSkyColor: 0x2d3e7f,
		cloudsCloudColor: 0xffffff,
		cloudsCloudShadowColor: 0x2f2f2f,
		cloudsSunColor: 0xffcc66,
		cloudsSunGlareColor: 0xff6633,
		cloudsSunlightColor: 0xff9933,
		cloudsSpeed: 1,
		cloudsMouseControls: true,
		cloudsTouchControls: true,
		cloudsGyroControls: false,
		cloudsMinHeight: 200,
		cloudsMinWidth: 200,
		clouds2Scale: 1,
		clouds2Speed: 1,
		clouds2TexturePath: '/backgrounds/noise.png',
		clouds2SkyColor: 0x68b8d7,
		clouds2CloudColor: 0xadc1de,
		clouds2LightColor: 0xffffff,
		clouds2BackgroundColor: 0x0,
		clouds2MouseControls: true,
		clouds2TouchControls: true,
		clouds2GyroControls: false,
		clouds2MinHeight: 200,
		clouds2MinWidth: 200,
	}

	let selected = $state<BackgroundType>('clouds2')
	let config = $state<BackgroundConfig>(DEFAULT_CONFIG)

	if (browser) {
		const rawSelected = localStorage.getItem(STORAGE_SELECTED)
		if (rawSelected && backgrounds.includes(rawSelected as BackgroundType)) {
			selected = rawSelected as BackgroundType
		}
		const rawConfig = localStorage.getItem(STORAGE_CONFIG)
		if (rawConfig) {
			try {
				const parsed = JSON.parse(rawConfig) as BackgroundConfig
				config = { ...DEFAULT_CONFIG, ...parsed }
			} catch {
				// ignore invalid local storage
			}
		}
	}

	$effect(() => {
		background.setPage(selected)
	})

	$effect(() => {
		background.setPageConfig(config)
	})

	$effect(() => {
		if (!browser) return
		localStorage.setItem(STORAGE_SELECTED, selected)
		localStorage.setItem(STORAGE_CONFIG, JSON.stringify(config))
	})

	onDestroy(() => {
		background.clearPageConfig()
		background.clearPage()
	})

	const configJson = $derived(JSON.stringify(config, null, 2))

	const raysOrigins = [
		'top-center',
		'top-left',
		'top-right',
		'right',
		'left',
		'bottom-center',
		'bottom-right',
		'bottom-left',
	] as const

	function toHex(value: number | undefined): string {
		if (value === undefined) return '#000000'
		const safe = Math.max(0, Math.min(0xffffff, value))
		return `#${safe.toString(16).padStart(6, '0')}`
	}

	function fromHex(value: string): number {
		return Number.parseInt(value.replace('#', ''), 16)
	}

	function setColor(key: keyof BackgroundConfig, value: string) {
		const next = fromHex(value)
		config = { ...config, [key]: next }
	}

	function setNumber(key: keyof BackgroundConfig, value: string) {
		const next = Number(value)
		if (!Number.isFinite(next)) return
		config = { ...config, [key]: next }
	}

	function setString(key: keyof BackgroundConfig, value: string) {
		config = { ...config, [key]: value }
	}

	function setBoolean(key: keyof BackgroundConfig, value: boolean) {
		config = { ...config, [key]: value }
	}

	function copyConfig() {
		if (!browser) return
		void navigator.clipboard.writeText(configJson)
	}

	function resetConfig() {
		if (!browser) return
		localStorage.removeItem(STORAGE_CONFIG)
		localStorage.removeItem(STORAGE_SELECTED)
		window.location.reload()
	}
</script>

<div class="mx-auto w-full max-w-3xl px-4 pt-8 pb-24 sm:px-6">
	<div class="space-y-2">
		<h1 class="text-xl font-semibold">backgrounds debug</h1>
		<p class="text-muted-foreground text-sm">
			this page controls the live app background directly. tweak settings here, then copy JSON
			and paste into frontend/src/routes/+layout.svelte DEFAULT_BACKGROUND_CONFIG.
		</p>
	</div>

	<div class="mt-5 flex flex-wrap items-center gap-2">
		<a
			href={resolve('/debug')}
			class="rounded-xl border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-sm text-foreground/80 transition hover:border-foreground/20 hover:bg-foreground/8"
		>
			back to debug
		</a>
		<button
			type="button"
			onclick={copyConfig}
			class="rounded-xl border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-sm text-foreground/80 transition hover:border-foreground/20 hover:bg-foreground/8"
		>
			copy json
		</button>
		<button
			type="button"
			onclick={resetConfig}
			class="rounded-xl border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-sm text-foreground/80 transition hover:border-foreground/20 hover:bg-foreground/8"
		>
			reset
		</button>
	</div>

	<div class="mt-6 space-y-4">
		<div class="rounded-2xl border border-foreground/10 bg-foreground/5 p-4">
			<div class="mb-2 text-xs text-foreground/60">background</div>
			<select
				class="w-full rounded-lg border border-foreground/15 bg-black/40 px-3 py-2 text-sm"
				value={selected}
				onchange={(e) => {
					selected = e.currentTarget.value as BackgroundType
				}}
			>
				{#each backgrounds as bg (bg)}
					<option value={bg}>{bg}</option>
				{/each}
			</select>
		</div>

		{#if selected === 'static'}
			<div class="rounded-2xl border border-foreground/10 bg-foreground/5 p-4">
				<div class="mb-2 text-xs text-foreground/60">color</div>
				<input
					type="color"
					value={config.color || '#171717'}
					oninput={(e) => setString('color', e.currentTarget.value)}
				/>
			</div>
		{:else if selected === 'lightbends'}
			<div class="space-y-3 rounded-2xl border border-foreground/10 bg-foreground/5 p-4">
				<div class="text-xs text-foreground/60">speed</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.lightBendsSpeed || 0.2}
					oninput={(e) => setNumber('lightBendsSpeed', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">warp</div>
				<input
					type="range"
					min="0"
					max="3"
					step="0.05"
					value={config.lightBendsWarp || 1}
					oninput={(e) => setNumber('lightBendsWarp', e.currentTarget.value)}
				/>
			</div>
		{:else if selected === 'lightrays'}
			<div class="space-y-3 rounded-2xl border border-foreground/10 bg-foreground/5 p-4">
				<div class="text-xs text-foreground/60">origin</div>
				<select
					class="w-full rounded-lg border border-foreground/15 bg-black/40 px-3 py-2 text-sm"
					value={config.raysOrigin || 'top-center'}
					onchange={(e) => setString('raysOrigin', e.currentTarget.value)}
				>
					{#each raysOrigins as origin (origin)}
						<option value={origin}>{origin}</option>
					{/each}
				</select>
				<div class="text-xs text-foreground/60">color</div>
				<input
					type="color"
					value={config.raysColor || '#ffffff'}
					oninput={(e) => setString('raysColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">speed</div>
				<input
					type="range"
					min="0"
					max="3"
					step="0.05"
					value={config.raysSpeed || 1}
					oninput={(e) => setNumber('raysSpeed', e.currentTarget.value)}
				/>
			</div>
		{:else if selected === 'silk'}
			<div class="space-y-3 rounded-2xl border border-foreground/10 bg-foreground/5 p-4">
				<div class="text-xs text-foreground/60">color</div>
				<input
					type="color"
					value={config.silkColor || '#7B7481'}
					oninput={(e) => setString('silkColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">speed</div>
				<input
					type="range"
					min="0"
					max="10"
					step="0.1"
					value={config.silkSpeed || 5}
					oninput={(e) => setNumber('silkSpeed', e.currentTarget.value)}
				/>
			</div>
		{:else if selected === 'fog'}
			<div class="space-y-3 rounded-2xl border border-foreground/10 bg-foreground/5 p-4">
				<div class="text-xs text-foreground/60">mouse controls</div>
				<input
					type="checkbox"
					checked={config.fogMouseControls ?? true}
					onchange={(e) => setBoolean('fogMouseControls', e.currentTarget.checked)}
				/>
				<div class="text-xs text-foreground/60">touch controls</div>
				<input
					type="checkbox"
					checked={config.fogTouchControls ?? true}
					onchange={(e) => setBoolean('fogTouchControls', e.currentTarget.checked)}
				/>
				<div class="text-xs text-foreground/60">gyro controls</div>
				<input
					type="checkbox"
					checked={config.fogGyroControls ?? false}
					onchange={(e) => setBoolean('fogGyroControls', e.currentTarget.checked)}
				/>
				<div class="text-xs text-foreground/60">min height</div>
				<input
					type="number"
					min="1"
					step="1"
					value={config.fogMinHeight ?? 200}
					oninput={(e) => setNumber('fogMinHeight', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">min width</div>
				<input
					type="number"
					min="1"
					step="1"
					value={config.fogMinWidth ?? 200}
					oninput={(e) => setNumber('fogMinWidth', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">highlight color</div>
				<input
					type="color"
					value={toHex(config.fogHighlightColor)}
					oninput={(e) => setColor('fogHighlightColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">midtone color</div>
				<input
					type="color"
					value={toHex(config.fogMidtoneColor)}
					oninput={(e) => setColor('fogMidtoneColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">lowlight color</div>
				<input
					type="color"
					value={toHex(config.fogLowlightColor)}
					oninput={(e) => setColor('fogLowlightColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">base color</div>
				<input
					type="color"
					value={toHex(config.fogBaseColor)}
					oninput={(e) => setColor('fogBaseColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">blur factor</div>
				<input
					type="range"
					min="0"
					max="2"
					step="0.01"
					value={config.fogBlurFactor || 0.6}
					oninput={(e) => setNumber('fogBlurFactor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">speed</div>
				<input
					type="range"
					min="0"
					max="3"
					step="0.01"
					value={config.fogSpeed || 1}
					oninput={(e) => setNumber('fogSpeed', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">zoom</div>
				<input
					type="range"
					min="0.1"
					max="3"
					step="0.01"
					value={config.fogZoom || 1}
					oninput={(e) => setNumber('fogZoom', e.currentTarget.value)}
				/>
			</div>
		{:else if selected === 'clouds'}
			<div class="space-y-3 rounded-2xl border border-foreground/10 bg-foreground/5 p-4">
				<div class="text-xs text-foreground/60">mouse controls</div>
				<input
					type="checkbox"
					checked={config.cloudsMouseControls ?? true}
					onchange={(e) => setBoolean('cloudsMouseControls', e.currentTarget.checked)}
				/>
				<div class="text-xs text-foreground/60">touch controls</div>
				<input
					type="checkbox"
					checked={config.cloudsTouchControls ?? true}
					onchange={(e) => setBoolean('cloudsTouchControls', e.currentTarget.checked)}
				/>
				<div class="text-xs text-foreground/60">gyro controls</div>
				<input
					type="checkbox"
					checked={config.cloudsGyroControls ?? false}
					onchange={(e) => setBoolean('cloudsGyroControls', e.currentTarget.checked)}
				/>
				<div class="text-xs text-foreground/60">min height</div>
				<input
					type="number"
					min="1"
					step="1"
					value={config.cloudsMinHeight ?? 200}
					oninput={(e) => setNumber('cloudsMinHeight', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">min width</div>
				<input
					type="number"
					min="1"
					step="1"
					value={config.cloudsMinWidth ?? 200}
					oninput={(e) => setNumber('cloudsMinWidth', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">sky color</div>
				<input
					type="color"
					value={toHex(config.cloudsSkyColor)}
					oninput={(e) => setColor('cloudsSkyColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">cloud color</div>
				<input
					type="color"
					value={toHex(config.cloudsCloudColor)}
					oninput={(e) => setColor('cloudsCloudColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">cloud shadow color</div>
				<input
					type="color"
					value={toHex(config.cloudsCloudShadowColor)}
					oninput={(e) => setColor('cloudsCloudShadowColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">sun color</div>
				<input
					type="color"
					value={toHex(config.cloudsSunColor)}
					oninput={(e) => setColor('cloudsSunColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">sun glare color</div>
				<input
					type="color"
					value={toHex(config.cloudsSunGlareColor)}
					oninput={(e) => setColor('cloudsSunGlareColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">sunlight color</div>
				<input
					type="color"
					value={toHex(config.cloudsSunlightColor)}
					oninput={(e) => setColor('cloudsSunlightColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">speed</div>
				<input
					type="range"
					min="0"
					max="3"
					step="0.01"
					value={config.cloudsSpeed || 1}
					oninput={(e) => setNumber('cloudsSpeed', e.currentTarget.value)}
				/>
			</div>
		{:else if selected === 'clouds2'}
			<div class="space-y-3 rounded-2xl border border-foreground/10 bg-foreground/5 p-4">
				<div class="text-xs text-foreground/60">mouse controls</div>
				<input
					type="checkbox"
					checked={config.clouds2MouseControls ?? true}
					onchange={(e) => setBoolean('clouds2MouseControls', e.currentTarget.checked)}
				/>
				<div class="text-xs text-foreground/60">touch controls</div>
				<input
					type="checkbox"
					checked={config.clouds2TouchControls ?? true}
					onchange={(e) => setBoolean('clouds2TouchControls', e.currentTarget.checked)}
				/>
				<div class="text-xs text-foreground/60">gyro controls</div>
				<input
					type="checkbox"
					checked={config.clouds2GyroControls ?? false}
					onchange={(e) => setBoolean('clouds2GyroControls', e.currentTarget.checked)}
				/>
				<div class="text-xs text-foreground/60">min height</div>
				<input
					type="number"
					min="1"
					step="1"
					value={config.clouds2MinHeight ?? 200}
					oninput={(e) => setNumber('clouds2MinHeight', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">min width</div>
				<input
					type="number"
					min="1"
					step="1"
					value={config.clouds2MinWidth ?? 200}
					oninput={(e) => setNumber('clouds2MinWidth', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">texture path (empty disables noise)</div>
				<input
					class="w-full rounded-lg border border-foreground/15 bg-black/40 px-3 py-2 text-sm"
					type="text"
					value={config.clouds2TexturePath || ''}
					oninput={(e) => setString('clouds2TexturePath', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">scale</div>
				<input
					type="range"
					min="0.1"
					max="5"
					step="0.01"
					value={config.clouds2Scale || 1}
					oninput={(e) => setNumber('clouds2Scale', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">speed</div>
				<input
					type="range"
					min="0"
					max="3"
					step="0.01"
					value={config.clouds2Speed || 1}
					oninput={(e) => setNumber('clouds2Speed', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">sky color</div>
				<input
					type="color"
					value={toHex(config.clouds2SkyColor)}
					oninput={(e) => setColor('clouds2SkyColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">cloud color</div>
				<input
					type="color"
					value={toHex(config.clouds2CloudColor)}
					oninput={(e) => setColor('clouds2CloudColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">light color</div>
				<input
					type="color"
					value={toHex(config.clouds2LightColor)}
					oninput={(e) => setColor('clouds2LightColor', e.currentTarget.value)}
				/>
				<div class="text-xs text-foreground/60">background color</div>
				<input
					type="color"
					value={toHex(config.clouds2BackgroundColor)}
					oninput={(e) => setColor('clouds2BackgroundColor', e.currentTarget.value)}
				/>
			</div>
		{/if}

		<div class="rounded-2xl border border-foreground/10 bg-foreground/5 p-4">
			<div class="mb-2 text-xs text-foreground/60">config json</div>
			<pre
				class="max-h-64 overflow-auto rounded-lg border border-foreground/10 bg-black/35 p-3 text-xs text-foreground/80">{configJson}</pre>
		</div>
	</div>
</div>
