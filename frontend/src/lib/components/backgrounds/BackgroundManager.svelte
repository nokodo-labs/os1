<script lang="ts">
	import { untrack, type Snippet } from 'svelte'
	import StaticBackground from './StaticBackground.svelte'
	import DarkVeilBackground from './webgl/DarkVeilBackground.svelte'
	import GalaxyBackgroundWebGL from './webgl/GalaxyBackgroundWebGL.svelte'
	import LightBendsBackground from './webgl/LightBendsBackground.svelte'
	import LightRaysBackground from './webgl/LightRaysBackground.svelte'
	import SilkBackground from './webgl/SilkBackground.svelte'

	export type BackgroundType =
		| 'galaxy'
		| 'darkveil'
		| 'lightbends'
		| 'lightrays'
		| 'silk'
		| 'static'
		| 'none'

	interface BackgroundConfig {
		// Static background options
		color?: string
		image?: string

		// LightBends options
		lightBendsColors?: string[]
		lightBendsSpeed?: number
		lightBendsWarp?: number

		// LightRays options
		raysOrigin?:
			| 'top-center'
			| 'top-left'
			| 'top-right'
			| 'right'
			| 'left'
			| 'bottom-center'
			| 'bottom-right'
			| 'bottom-left'
		raysColor?: string
		raysSpeed?: number

		// Silk options
		silkColor?: string
		silkSpeed?: number

		// Add more as needed...
	}

	interface Props {
		type: BackgroundType
		config?: BackgroundConfig
		children?: Snippet
		onReady?: () => void
	}

	let { type = 'galaxy', config = {}, children, onReady }: Props = $props()

	let readySent = $state(false)
	function signalReady() {
		if (readySent) return
		readySent = true
		onReady?.()
	}

	// Transition state for smooth swapping
	let currentBg = $state<BackgroundType>('galaxy')
	currentBg = untrack(() => type)
	let previousBg = $state<BackgroundType | null>(null)
	let isTransitioning = $state(false)

	$effect(() => {
		if (type !== currentBg && !isTransitioning) {
			isTransitioning = true
			previousBg = currentBg

			// Use rAF to batch the state update with the next paint,
			// then a single timeout for the cross-fade duration.
			requestAnimationFrame(() => {
				currentBg = type
				setTimeout(() => {
					previousBg = null
					isTransitioning = false
				}, 300) // match CSS transition duration
			})
		}
	})

	$effect(() => {
		if (readySent) return
		if (currentBg === 'static' || currentBg === 'none') {
			signalReady()
		}
	})
</script>

<!-- Background layers - positioned absolutely -->
<div class="fixed inset-0 -z-10">
	{#if previousBg && isTransitioning}
		<div class="absolute inset-0" style="opacity: 1; transition: opacity 300ms ease-in-out;">
			{#if previousBg === 'galaxy'}
				<GalaxyBackgroundWebGL />
			{:else if previousBg === 'darkveil'}
				<DarkVeilBackground />
			{:else if previousBg === 'lightbends'}
				<LightBendsBackground
					colors={config.lightBendsColors || ['#ff0080', '#0080ff', '#00ff80']}
					speed={config.lightBendsSpeed || 0.2}
					warpStrength={config.lightBendsWarp || 1}
				/>
			{:else if previousBg === 'lightrays'}
				<LightRaysBackground
					raysOrigin={config.raysOrigin || 'top-center'}
					raysColor={config.raysColor || '#ffffff'}
					raysSpeed={config.raysSpeed || 1}
				/>
			{:else if previousBg === 'silk'}
				<SilkBackground
					color={config.silkColor || '#7B7481'}
					speed={config.silkSpeed || 5}
				/>
			{:else if previousBg === 'static'}
				<StaticBackground color={config.color || '#000000'} image={config.image} />
			{/if}
		</div>
	{/if}

	<div class="absolute inset-0" style="opacity: 1; transition: opacity 300ms ease-in-out;">
		{#if currentBg === 'galaxy'}
			<GalaxyBackgroundWebGL onReady={signalReady}>
				{#if children}
					{@render children()}
				{/if}
			</GalaxyBackgroundWebGL>
		{:else if currentBg === 'darkveil'}
			<DarkVeilBackground onReady={signalReady}>
				{#if children}
					{@render children()}
				{/if}
			</DarkVeilBackground>
		{:else if currentBg === 'lightbends'}
			<LightBendsBackground
				colors={config.lightBendsColors || ['#ff0080', '#0080ff', '#00ff80']}
				speed={config.lightBendsSpeed || 0.2}
				warpStrength={config.lightBendsWarp || 1}
				onReady={signalReady}
			>
				{#if children}
					{@render children()}
				{/if}
			</LightBendsBackground>
		{:else if currentBg === 'lightrays'}
			<LightRaysBackground
				raysOrigin={config.raysOrigin || 'top-center'}
				raysColor={config.raysColor || '#ffffff'}
				raysSpeed={config.raysSpeed || 1}
				onReady={signalReady}
			>
				{#if children}
					{@render children()}
				{/if}
			</LightRaysBackground>
		{:else if currentBg === 'silk'}
			<SilkBackground
				color={config.silkColor || '#7B7481'}
				speed={config.silkSpeed || 5}
				onReady={signalReady}
			>
				{#if children}
					{@render children()}
				{/if}
			</SilkBackground>
		{:else if currentBg === 'static'}
			<StaticBackground color={config.color || '#000000'} image={config.image}>
				{#if children}
					{@render children()}
				{/if}
			</StaticBackground>
		{:else if currentBg === 'none' && children}
			<div class="relative z-1">
				{@render children()}
			</div>
		{/if}
	</div>
</div>
