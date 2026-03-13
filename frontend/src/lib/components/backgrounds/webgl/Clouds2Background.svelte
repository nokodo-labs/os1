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
		scale?: number
		speed?: number
		texturePath?: string | null
		skyColor?: number
		cloudColor?: number
		lightColor?: number
		backgroundColor?: number
	}

	let {
		children,
		onReady,
		mouseControls = true,
		touchControls = true,
		gyroControls = false,
		minHeight = 200,
		minWidth = 200,
		scale = 1,
		speed,
		texturePath = '/backgrounds/noise.png',
		skyColor,
		cloudColor,
		lightColor,
		backgroundColor,
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
			scale,
			speed,
			texturePath,
			skyColor,
			cloudColor,
			lightColor,
			backgroundColor,
		]
		if (!containerRef) return

		const token = ++initToken
		vantaEffect?.destroy?.()
		vantaEffect = null

		const el = containerRef
		void (async () => {
			const vanta = await ensureVanta('/backgrounds/vanta.clouds2.min.js')
			const createClouds2 = vanta.CLOUDS2
			if (!createClouds2) throw new Error('vanta clouds2 is unavailable')
			if (!el || token !== initToken) return

			const options: Record<string, unknown> = {
				el: el,
				mouseControls,
				touchControls,
				gyroControls,
				minHeight,
				minWidth,
				scale,
			}

			if (speed !== undefined) options.speed = speed
			if (texturePath) options.texturePath = texturePath
			if (skyColor !== undefined) options.skyColor = skyColor
			if (cloudColor !== undefined) options.cloudColor = cloudColor
			if (lightColor !== undefined) options.lightColor = lightColor
			if (backgroundColor !== undefined) options.backgroundColor = backgroundColor

			const effect = createClouds2(options)
			if (token !== initToken) {
				effect?.destroy?.()
				return
			}

			vantaEffect = effect
			signalReady()
		})().catch((error) => {
			console.error('failed to initialize clouds2 background:', error)
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
