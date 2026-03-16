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
		highlightColor?: number
		midtoneColor?: number
		lowlightColor?: number
		baseColor?: number
		blurFactor?: number
		speed?: number
		zoom?: number
	}

	let {
		children,
		onReady,
		mouseControls = true,
		touchControls = true,
		gyroControls = false,
		minHeight = 200,
		minWidth = 200,
		highlightColor,
		midtoneColor,
		lowlightColor,
		baseColor,
		blurFactor,
		speed,
		zoom,
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
			highlightColor,
			midtoneColor,
			lowlightColor,
			baseColor,
			blurFactor,
			speed,
			zoom,
		]
		if (!containerRef) return

		const token = ++initToken
		vantaEffect?.destroy?.()
		vantaEffect = null

		const el = containerRef
		void (async () => {
			const vanta = await ensureVanta('/backgrounds/vanta.fog.min.js')
			const createFog = vanta.FOG
			if (!createFog) throw new Error('vanta fog is unavailable')
			if (!el || token !== initToken) return

			const options: Record<string, unknown> = {
				el: el,
				mouseControls,
				touchControls,
				gyroControls,
				minHeight,
				minWidth,
			}

			if (highlightColor !== undefined) options.highlightColor = highlightColor
			if (midtoneColor !== undefined) options.midtoneColor = midtoneColor
			if (lowlightColor !== undefined) options.lowlightColor = lowlightColor
			if (baseColor !== undefined) options.baseColor = baseColor
			if (blurFactor !== undefined) options.blurFactor = blurFactor
			if (speed !== undefined) options.speed = speed
			if (zoom !== undefined) options.zoom = zoom

			const effect = createFog(options)
			if (token !== initToken) {
				effect?.destroy?.()
				return
			}

			vantaEffect = effect
			signalReady()
		})().catch((error) => {
			console.error('failed to initialize fog background:', error)
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
