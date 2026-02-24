<script lang="ts">
	import { ensureVanta } from '$lib/components/backgrounds/webgl/vantaLoader'
	import { createOnceCallback } from '$lib/utils/once'
	import type { Snippet } from 'svelte'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
		children?: Snippet
		onReady?: () => void
		mouseControls?: boolean
		touchControls?: boolean
		gyroControls?: boolean
		minHeight?: number
		minWidth?: number
		skyColor?: number
		cloudColor?: number
		cloudShadowColor?: number
		sunColor?: number
		sunGlareColor?: number
		sunlightColor?: number
		speed?: number
	}

	let {
		children,
		onReady,
		mouseControls = true,
		touchControls = true,
		gyroControls = false,
		minHeight = 200,
		minWidth = 200,
		skyColor,
		cloudColor,
		cloudShadowColor,
		sunColor,
		sunGlareColor,
		sunlightColor,
		speed,
	}: Props = $props()
	const signalReady = createOnceCallback(() => onReady?.())

	let containerRef: HTMLDivElement
	let vantaEffect: { destroy?: () => void } | null = null
	let initToken = 0

	$effect(() => {
		void [
			mouseControls,
			touchControls,
			gyroControls,
			minHeight,
			minWidth,
			skyColor,
			cloudColor,
			cloudShadowColor,
			sunColor,
			sunGlareColor,
			sunlightColor,
			speed,
		]
		if (!containerRef) return

		const token = ++initToken
		vantaEffect?.destroy?.()
		vantaEffect = null

		void (async () => {
			const vanta = await ensureVanta('/backgrounds/vanta.clouds.min.js')
			const createClouds = vanta.CLOUDS
			if (!createClouds) throw new Error('vanta clouds is unavailable')

			const options: Record<string, unknown> = {
				el: containerRef,
				mouseControls,
				touchControls,
				gyroControls,
				minHeight,
				minWidth,
			}

			if (skyColor !== undefined) options.skyColor = skyColor
			if (cloudColor !== undefined) options.cloudColor = cloudColor
			if (cloudShadowColor !== undefined) options.cloudShadowColor = cloudShadowColor
			if (sunColor !== undefined) options.sunColor = sunColor
			if (sunGlareColor !== undefined) options.sunGlareColor = sunGlareColor
			if (sunlightColor !== undefined) options.sunlightColor = sunlightColor
			if (speed !== undefined) options.speed = speed

			const effect = createClouds(options)
			if (token !== initToken) {
				effect?.destroy?.()
				return
			}

			vantaEffect = effect
			signalReady()
		})().catch((error) => {
			console.error('failed to initialize clouds background:', error)
			signalReady()
		})
	})

	onMount(() => {
		return () => {
			initToken += 1
			vantaEffect?.destroy?.()
			vantaEffect = null
		}
	})

	onDestroy(() => {
		vantaEffect?.destroy?.()
		vantaEffect = null
	})
</script>

<div class="vanta-bg" bind:this={containerRef}></div>
{#if children}
	<div class="relative z-1 h-full w-full">
		{@render children()}
	</div>
{/if}

<style>
	.vanta-bg {
		position: absolute;
		inset: 0;
		height: 100%;
		width: 100%;
	}
</style>
