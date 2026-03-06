<script lang="ts">
	import { createOnceCallback } from '$lib/utils/once'
	import { Mesh, Program, Renderer, Triangle } from 'ogl'
	import type { Snippet } from 'svelte'
	import { untrack } from 'svelte'

	interface Props {
		children?: Snippet
		onReady?: () => void
		color?: [number, number, number]
		speed?: number
		amplitude?: number
		mouseReact?: boolean
	}

	let {
		children,
		onReady,
		color = [1, 1, 1],
		speed = 1.0,
		amplitude = 0.1,
		mouseReact = true,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	let canvasRef: HTMLCanvasElement
	let containerRef: HTMLDivElement
	// holds the active OGL program so a second effect can update uniforms in-place
	let programRef = $state<Program | null>(null)

	const vertex = /* glsl */ `
attribute vec2 uv;
attribute vec2 position;
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position, 0, 1);
}
`

	const fragment = /* glsl */ `
precision highp float;
uniform float uTime;
uniform vec3 uColor;
uniform vec3 uResolution;
uniform vec2 uMouse;
uniform float uAmplitude;
uniform float uSpeed;
varying vec2 vUv;
void main() {
  float mr = min(uResolution.x, uResolution.y);
  vec2 uv = (vUv.xy * 2.0 - 1.0) * uResolution.xy / mr;
  uv += (uMouse - vec2(0.5)) * uAmplitude;
  float d = -uTime * 0.5 * uSpeed;
  float a = 0.0;
  for (float i = 0.0; i < 8.0; ++i) {
    a += cos(i - d - a * uv.x);
    d += sin(uv.y * i + a);
  }
  d += uTime * 0.5 * uSpeed;
  vec3 col = vec3(cos(uv * vec2(d, a)) * 0.6 + 0.4, cos(a + d) * 0.5 + 0.5);
  col = cos(col * cos(vec3(d, a, 2.5)) * 0.5 + 0.5) * uColor;
  gl_FragColor = vec4(col, 1.0);
}
`

	// setup: runs once when the canvas/container are ready
	$effect(() => {
		if (!canvasRef || !containerRef) return

		// pass svelte-owned canvas to OGL - no DOM manipulation needed
		const renderer = new Renderer({ canvas: canvasRef, alpha: true })
		const gl = renderer.gl
		gl.clearColor(1, 1, 1, 1)

		const geometry = new Triangle(gl)

		const initColor = untrack(() => color)
		const colorArr = new Float32Array(initColor)
		const resArr = new Float32Array([
			gl.canvas.width,
			gl.canvas.height,
			gl.canvas.width / gl.canvas.height,
		])
		const mouseArr = new Float32Array([0.5, 0.5])

		const program = new Program(gl, {
			vertex,
			fragment,
			uniforms: {
				uTime: { value: 0 },
				uColor: { value: colorArr },
				uResolution: { value: resArr },
				uMouse: { value: mouseArr },
				uAmplitude: { value: untrack(() => amplitude) },
				uSpeed: { value: untrack(() => speed) },
			},
		})

		programRef = program

		const mesh = new Mesh(gl, { geometry, program })

		function resize() {
			renderer.setSize(containerRef.offsetWidth, containerRef.offsetHeight)
			const res = program.uniforms.uResolution.value as Float32Array
			res[0] = gl.canvas.width
			res[1] = gl.canvas.height
			res[2] = gl.canvas.width / gl.canvas.height
		}

		const ro = new ResizeObserver(resize)
		ro.observe(containerRef)
		resize()

		let raf = 0
		function update(t: number) {
			raf = requestAnimationFrame(update)
			program.uniforms.uTime.value = t * 0.001
			renderer.render({ scene: mesh })
		}
		raf = requestAnimationFrame(update)
		signalReady()

		function handleMouseMove(e: MouseEvent) {
			const rect = containerRef.getBoundingClientRect()
			const mx = (e.clientX - rect.left) / rect.width
			const my = 1.0 - (e.clientY - rect.top) / rect.height
			const mouse = program.uniforms.uMouse.value as Float32Array
			mouse[0] = mx
			mouse[1] = my
		}

		if (untrack(() => mouseReact)) containerRef.addEventListener('mousemove', handleMouseMove)

		return () => {
			programRef = null
			cancelAnimationFrame(raf)
			ro.disconnect()
			containerRef.removeEventListener('mousemove', handleMouseMove)
			gl.getExtension('WEBGL_lose_context')?.loseContext()
		}
	})

	// uniform updates: runs whenever props change without recreating the renderer
	$effect(() => {
		if (!programRef) return
		;(programRef.uniforms.uColor.value as Float32Array).set(color)
		programRef.uniforms.uSpeed.value = speed
		programRef.uniforms.uAmplitude.value = amplitude
	})
</script>

<div class="absolute inset-0 overflow-hidden" bind:this={containerRef}>
	<canvas class="pointer-events-none absolute inset-0 block h-full w-full" bind:this={canvasRef}
	></canvas>
	{#if children}
		<div class="relative z-1 h-full w-full">
			{@render children()}
		</div>
	{/if}
</div>
