<script lang="ts">
	import {
		ensureVanta,
		pauseVantaWhileHidden,
		syncVantaFrameLoop,
		type VantaEffect,
	} from '$lib/components/backgrounds/webgl/vantaLoader'
	import { createOnceCallback } from '$lib/utils/once'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
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
	let vantaEffect: VantaEffect | null = null
	let initToken = 0
	const stopVisibilitySync = pauseVantaWhileHidden(() => vantaEffect)

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

		const el = containerRef
		void (async () => {
			const vanta = await ensureVanta('/backgrounds/vanta.clouds.min.js')
			const createClouds = vanta.CLOUDS
			if (!createClouds) throw new Error('vanta clouds is unavailable')
			if (!el || token !== initToken) return

			const options: Record<string, unknown> = {
				el: el,
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
			syncVantaFrameLoop(effect)
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
		stopVisibilitySync()
		vantaEffect?.destroy?.()
		vantaEffect = null
	})
</script>

<div class="vanta-bg" bind:this={containerRef}></div>

<style>
	.vanta-bg {
		position: absolute;
		inset: 0;
		height: 100%;
		width: 100%;
	}
</style>
