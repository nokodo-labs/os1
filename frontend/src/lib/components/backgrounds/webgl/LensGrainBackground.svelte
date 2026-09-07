<script lang="ts">
	// ported from hermes (nousresearch/hermes-agent, MIT) skills/creative/pretext/templates/donut-orbit.html
	import { startWallpaperLoop } from '$lib/components/backgrounds/wallpaperLoop'
	import { createOnceCallback } from '$lib/utils/once'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
		onReady?: () => void
		color?: string
		backgroundColor?: string
		density?: number
		opacity?: number
		size?: number
		animated?: boolean
		vignetteColor?: string
		vignetteOpacity?: number
	}

	let {
		onReady,
		color = '#eaeaea',
		backgroundColor = '#041c1c',
		density = 0.11,
		opacity = 0.25,
		size = 1,
		animated = true,
		vignetteColor = '#ffbd38',
		vignetteOpacity = 0.22,
	}: Props = $props()

	const signalReady = createOnceCallback(() => onReady?.())

	// the grain is a dither pattern, not motion - resampling it faster reads as noise
	const MAX_FPS = 24

	const vertexShaderSource = `#version 300 es
in vec2 aPos;
out vec2 vUv;

void main() {
	vUv = aPos * 0.5 + 0.5;
	gl_Position = vec4(aPos, 0.0, 1.0);
}`

	const fragmentShaderSource = `#version 300 es
precision mediump float;

in vec2 vUv;
uniform vec2 uRes;
uniform float uDpr;
uniform float uSize;
uniform float uDensity;
uniform float uOpacity;
uniform float uSeed;
uniform vec3 uColor;
out vec4 fragColor;

float hash(vec2 p) {
	vec3 p3 = fract(vec3(p.xyx) * 0.1031);
	p3 += dot(p3, p3.yzx + 33.33);
	return fract((p3.x + p3.y) * p3.z);
}

void main() {
	float n = hash(floor(vUv * uRes / (uSize * uDpr)) + uSeed);
	fragColor = vec4(uColor, step(1.0 - uDensity, n)) * uOpacity;
}`

	interface GrainUniforms {
		uRes: WebGLUniformLocation | null
		uDpr: WebGLUniformLocation | null
		uSize: WebGLUniformLocation | null
		uDensity: WebGLUniformLocation | null
		uOpacity: WebGLUniformLocation | null
		uSeed: WebGLUniformLocation | null
		uColor: WebGLUniformLocation | null
	}

	let containerRef: HTMLDivElement
	let canvasRef: HTMLCanvasElement
	let gl: WebGL2RenderingContext | null = null
	let program: WebGLProgram | null = null
	let uniforms: GrainUniforms | null = null
	let stopFrameLoop: (() => void) | null = null
	let resizeObserver: ResizeObserver | null = null
	let dpr = 1

	function hexToRgb(hex: string): [number, number, number] {
		const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
		if (!m) return [1, 1, 1]
		return [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255]
	}

	function createShader(
		context: WebGL2RenderingContext,
		type: number,
		source: string
	): WebGLShader | null {
		const shader = context.createShader(type)
		if (!shader) return null

		context.shaderSource(shader, source)
		context.compileShader(shader)

		if (!context.getShaderParameter(shader, context.COMPILE_STATUS)) {
			console.error('shader compile error:', context.getShaderInfoLog(shader))
			context.deleteShader(shader)
			return null
		}

		return shader
	}

	function resize(): void {
		if (!gl || !program || !uniforms || !containerRef || !canvasRef) return

		dpr = Math.min(window.devicePixelRatio || 1, 2)
		const rect = containerRef.getBoundingClientRect()
		const width = Math.max(1, Math.floor(rect.width * dpr))
		const height = Math.max(1, Math.floor(rect.height * dpr))

		if (canvasRef.width !== width || canvasRef.height !== height) {
			canvasRef.width = width
			canvasRef.height = height
		}

		gl.viewport(0, 0, width, height)
		gl.useProgram(program)
		gl.uniform2f(uniforms.uRes, width, height)
		gl.uniform1f(uniforms.uDpr, dpr)
	}

	function render(nowMs: number): void {
		if (!gl || !program || !uniforms) return

		gl.clear(gl.COLOR_BUFFER_BIT)
		gl.useProgram(program)

		const [r, g, b] = hexToRgb(color)
		gl.uniform1f(uniforms.uSize, Math.max(0.1, size))
		gl.uniform1f(uniforms.uDensity, density)
		gl.uniform1f(uniforms.uOpacity, opacity)
		gl.uniform1f(uniforms.uSeed, animated ? Math.floor(nowMs / (1000 / MAX_FPS)) : 0)
		gl.uniform3f(uniforms.uColor, r, g, b)
		gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
	}

	onMount(() => {
		const context = canvasRef.getContext('webgl2', { alpha: true, premultipliedAlpha: true })
		if (!context) {
			console.error('WebGL2 not supported')
			signalReady()
			return
		}

		gl = context
		const vertexShader = createShader(gl, gl.VERTEX_SHADER, vertexShaderSource)
		const fragmentShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource)
		if (!vertexShader || !fragmentShader) {
			signalReady()
			return
		}

		const prog = gl.createProgram()
		if (!prog) {
			signalReady()
			return
		}

		gl.attachShader(prog, vertexShader)
		gl.attachShader(prog, fragmentShader)
		gl.linkProgram(prog)
		if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
			console.error('program link error:', gl.getProgramInfoLog(prog))
			gl.deleteProgram(prog)
			signalReady()
			return
		}

		program = prog
		gl.useProgram(program)

		const buffer = gl.createBuffer()
		gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
		gl.bufferData(
			gl.ARRAY_BUFFER,
			new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
			gl.STATIC_DRAW
		)
		const positionLoc = gl.getAttribLocation(program, 'aPos')
		gl.enableVertexAttribArray(positionLoc)
		gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0)

		uniforms = {
			uRes: gl.getUniformLocation(program, 'uRes'),
			uDpr: gl.getUniformLocation(program, 'uDpr'),
			uSize: gl.getUniformLocation(program, 'uSize'),
			uDensity: gl.getUniformLocation(program, 'uDensity'),
			uOpacity: gl.getUniformLocation(program, 'uOpacity'),
			uSeed: gl.getUniformLocation(program, 'uSeed'),
			uColor: gl.getUniformLocation(program, 'uColor'),
		}

		// premultiplied source over a transparent canvas, so the grain composites
		// against the base color through the difference blend below
		gl.enable(gl.BLEND)
		gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
		gl.clearColor(0, 0, 0, 0)

		resize()
		resizeObserver = new ResizeObserver(() => resize())
		resizeObserver.observe(containerRef)

		stopFrameLoop = startWallpaperLoop(render, { maxFps: MAX_FPS })
		requestAnimationFrame(() => signalReady())
	})

	onDestroy(() => {
		stopFrameLoop?.()
		stopFrameLoop = null
		resizeObserver?.disconnect()
		resizeObserver = null
		if (gl && program) gl.deleteProgram(program)
	})
</script>

<!-- isolate keeps both blend layers compositing against the base color, not the page -->
<div
	class="absolute inset-0 isolate overflow-hidden"
	style="background-color: {backgroundColor}"
	bind:this={containerRef}
>
	<div
		class="pointer-events-none absolute inset-0 mix-blend-lighten"
		style="opacity: {vignetteOpacity}; background: radial-gradient(ellipse at 0% 0%, color-mix(in srgb, {vignetteColor} 0%, transparent) 60%, color-mix(in srgb, {vignetteColor} 35%, transparent) 100%)"
	></div>

	<canvas
		class="pointer-events-none absolute inset-0 block h-full w-full mix-blend-difference"
		bind:this={canvasRef}
	></canvas>
</div>
