<script lang="ts">
	import { setBackgroundContext } from '$lib/contexts/backgroundContext'
	import type { Snippet } from 'svelte'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
		children?: Snippet
		speed?: number
		scale?: number
		color?: string
		noiseIntensity?: number
		rotation?: number
	}

	let {
		children,
		speed = 5,
		scale = 1,
		color = '#7B7481',
		noiseIntensity = 1.5,
		rotation = 0,
	}: Props = $props()

	let containerRef: HTMLDivElement
	let canvasRef: HTMLCanvasElement
	let gl: WebGL2RenderingContext | null = null
	let program: WebGLProgram | null = null
	let animationId: number | null = null
	let resizeObserver: ResizeObserver | null = null
	let startTime = 0
	let subscribers: Array<() => void> = []

	// Expose canvas to children via context
	setBackgroundContext({
		getCanvas: () => canvasRef,
		getCanvasDimensions: () => ({
			width: canvasRef?.width || 0,
			height: canvasRef?.height || 0,
		}),
		subscribe: (callback) => {
			subscribers.push(callback)
			return () => {
				subscribers = subscribers.filter((cb) => cb !== callback)
			}
		},
	})

	const vertexShaderSource = `#version 300 es
in vec2 a_position;
out vec2 vUv;
out vec3 vPosition;

void main() {
	vPosition = vec3(a_position, 0.0);
	vUv = a_position * 0.5 + 0.5;
	gl_Position = vec4(a_position, 0.0, 1.0);
}`

	const fragmentShaderSource = `#version 300 es
precision highp float;

in vec2 vUv;
in vec3 vPosition;

uniform float uTime;
uniform vec3 uColor;
uniform float uSpeed;
uniform float uScale;
uniform float uRotation;
uniform float uNoiseIntensity;

out vec4 fragColor;

const float e = 2.71828182845904523536;

float noise(vec2 texCoord) {
	float G = e;
	vec2 r = (G * sin(G * texCoord));
	return fract(r.x * r.y * (1.0 + texCoord.x));
}

vec2 rotateUvs(vec2 uv, float angle) {
	float c = cos(angle);
	float s = sin(angle);
	mat2 rot = mat2(c, -s, s, c);
	return rot * uv;
}

void main() {
	float rnd = noise(gl_FragCoord.xy);
	vec2 uv = rotateUvs(vUv * uScale, uRotation);
	vec2 tex = uv * uScale;
	float tOffset = uSpeed * uTime;

	tex.y += 0.03 * sin(8.0 * tex.x - tOffset);

	float pattern = 0.6 +
	                0.4 * sin(5.0 * (tex.x + tex.y +
	                                 cos(3.0 * tex.x + 5.0 * tex.y) +
	                                 0.02 * tOffset) +
	                         sin(20.0 * (tex.x + tex.y - 0.1 * tOffset)));

	vec4 col = vec4(uColor, 1.0) * vec4(pattern) - rnd / 15.0 * uNoiseIntensity;
	col.a = 1.0;
	fragColor = col;
}`

	function createShader(
		gl: WebGL2RenderingContext,
		type: number,
		source: string
	): WebGLShader | null {
		const shader = gl.createShader(type)
		if (!shader) return null

		gl.shaderSource(shader, source)
		gl.compileShader(shader)

		if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
			console.error('Shader compile error:', gl.getShaderInfoLog(shader))
			gl.deleteShader(shader)
			return null
		}

		return shader
	}

	function createProgram(
		gl: WebGL2RenderingContext,
		vertexShader: WebGLShader,
		fragmentShader: WebGLShader
	): WebGLProgram | null {
		const prog = gl.createProgram()
		if (!prog) return null

		gl.attachShader(prog, vertexShader)
		gl.attachShader(prog, fragmentShader)
		gl.linkProgram(prog)

		if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
			console.error('Program link error:', gl.getProgramInfoLog(prog))
			gl.deleteProgram(prog)
			return null
		}

		return prog
	}

	function hexToRgb(hex: string): { r: number; g: number; b: number } {
		const clean = hex.replace('#', '')
		const r = parseInt(clean.slice(0, 2), 16) / 255
		const g = parseInt(clean.slice(2, 4), 16) / 255
		const b = parseInt(clean.slice(4, 6), 16) / 255
		return { r, g, b }
	}

	function resize() {
		if (!canvasRef || !containerRef || !gl) return

		const dpr = Math.min(window.devicePixelRatio, 2)
		const rect = containerRef.getBoundingClientRect()
		const width = Math.floor(rect.width * dpr)
		const height = Math.floor(rect.height * dpr)

		if (canvasRef.width !== width || canvasRef.height !== height) {
			canvasRef.width = width
			canvasRef.height = height
			gl.viewport(0, 0, width, height)

			subscribers.forEach((cb) => cb())
		}
	}

	function animate() {
		if (!gl || !program) return

		resize()

		const elapsed = (performance.now() - startTime) / 1000
		// Match the original React implementation's time scale (0.1x)
		const scaledTime = elapsed * 0.1

		gl.clearColor(0, 0, 0, 1)
		gl.clear(gl.COLOR_BUFFER_BIT)

		gl.useProgram(program)

		// Set uniforms
		const uTime = gl.getUniformLocation(program, 'uTime')
		const uSpeed = gl.getUniformLocation(program, 'uSpeed')
		const uScale = gl.getUniformLocation(program, 'uScale')
		const uRotation = gl.getUniformLocation(program, 'uRotation')
		const uNoiseIntensity = gl.getUniformLocation(program, 'uNoiseIntensity')
		const uColor = gl.getUniformLocation(program, 'uColor')

		gl.uniform1f(uTime, scaledTime)
		gl.uniform1f(uSpeed, speed)
		gl.uniform1f(uScale, scale)
		gl.uniform1f(uRotation, rotation)
		gl.uniform1f(uNoiseIntensity, noiseIntensity)

		const rgb = hexToRgb(color)
		gl.uniform3f(uColor, rgb.r, rgb.g, rgb.b)

		gl.drawArrays(gl.TRIANGLES, 0, 6)

		animationId = requestAnimationFrame(animate)
	}

	onMount(() => {
		const context = canvasRef.getContext('webgl2')
		if (!context) {
			console.error('WebGL2 not supported')
			return
		}

		gl = context

		const vertexShader = createShader(gl, gl.VERTEX_SHADER, vertexShaderSource)
		const fragmentShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource)

		if (!vertexShader || !fragmentShader) {
			console.error('Failed to create shaders')
			return
		}

		program = createProgram(gl, vertexShader, fragmentShader)

		if (!program) {
			console.error('Failed to create program')
			return
		}

		// Create a fullscreen quad
		const positions = new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1])

		const positionBuffer = gl.createBuffer()
		gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
		gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW)

		const positionLoc = gl.getAttribLocation(program, 'a_position')
		gl.enableVertexAttribArray(positionLoc)
		gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0)

		// Setup resize observer
		resizeObserver = new ResizeObserver(() => resize())
		resizeObserver.observe(containerRef)

		startTime = performance.now()
		animate()
	})

	onDestroy(() => {
		if (animationId !== null) {
			cancelAnimationFrame(animationId)
		}

		if (resizeObserver) {
			resizeObserver.disconnect()
		}

		if (gl && program) {
			gl.deleteProgram(program)
		}
	})
</script>

<div class="absolute inset-0 overflow-hidden" bind:this={containerRef}>
	<canvas class="absolute inset-0 block h-full w-full" bind:this={canvasRef}></canvas>

	<!-- Slotted content rendered on top of background -->
	<div class="relative z-1 h-full w-full">
		{@render children?.()}
	</div>
</div>
