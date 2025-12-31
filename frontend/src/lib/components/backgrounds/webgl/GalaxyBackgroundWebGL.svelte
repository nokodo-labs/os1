<script lang="ts">
	import { setBackgroundContext } from '$lib/contexts/backgroundContext'
	import type { Snippet } from 'svelte'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
		children?: Snippet
	}

	let { children }: Props = $props()

	type GLShaderType =
		| WebGL2RenderingContext['VERTEX_SHADER']
		| WebGL2RenderingContext['FRAGMENT_SHADER']

	let containerRef: HTMLDivElement
	let canvasRef: HTMLCanvasElement
	let gl: WebGL2RenderingContext | null = null
	let program: WebGLProgram | null = null
	let animationId: number | null = null
	let resizeObserver: ResizeObserver | null = null
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
out vec2 v_uv;

void main() {
	v_uv = a_position * 0.5 + 0.5;
	gl_Position = vec4(a_position, 0.0, 1.0);
}`

	const fragmentShaderSource = `#version 300 es
precision highp float;

in vec2 v_uv;
out vec4 fragColor;

uniform float u_time;
uniform vec2 u_resolution;
uniform float u_focal_x;
uniform float u_focal_y;
uniform float u_rotation_x;
uniform float u_rotation_y;
uniform float u_star_speed;
uniform float u_density;
uniform float u_speed;
uniform float u_glow_intensity;
uniform float u_twinkle_intensity;
uniform float u_rotation_speed;

#define NUM_LAYER 4.0
#define MAT45 mat2(0.7071, -0.7071, 0.7071, 0.7071)
#define PERIOD 3.0

float Hash21(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

float tri(float x) {
	return abs(fract(x) * 2.0 - 1.0);
}

float tris(float x) {
	float t = fract(x);
	return 1.0 - smoothstep(0.0, 1.0, abs(2.0 * t - 1.0));
}

float trisn(float x) {
	float t = fract(x);
	return 2.0 * (1.0 - smoothstep(0.0, 1.0, abs(2.0 * t - 1.0))) - 1.0;
}

float Star(vec2 uv, float flare) {
	float d = length(uv);
	float m = (0.05 * u_glow_intensity) / d;
	float rays = smoothstep(0.0, 1.0, 1.0 - abs(uv.x * uv.y * 1000.0));
	m += rays * flare * u_glow_intensity;
	uv *= MAT45;
	rays = smoothstep(0.0, 1.0, 1.0 - abs(uv.x * uv.y * 1000.0));
	m += rays * 0.3 * flare * u_glow_intensity;
	m *= smoothstep(1.0, 0.2, d);
	return m;
}

vec3 StarLayer(vec2 uv) {
	vec3 col = vec3(0.0);
	
	vec2 gv = fract(uv) - 0.5;
	vec2 id = floor(uv);

	for (int y = -1; y <= 1; y++) {
		for (int x = -1; x <= 1; x++) {
			vec2 offset = vec2(float(x), float(y));
			vec2 si = id + offset;
			float seed = Hash21(si);
			float size = fract(seed * 345.32);
			float glossLocal = tri(u_star_speed / (PERIOD * seed + 1.0));
			float flareSize = smoothstep(0.9, 1.0, size) * glossLocal;

			// White/gray stars only - no color
			float brightness = 0.8 + seed * 0.2; // Slight variation in brightness
			vec3 starColor = vec3(brightness);

			vec2 pad = vec2(
				tris(seed * 34.0 + u_time * u_speed / 10.0),
				tris(seed * 38.0 + u_time * u_speed / 30.0)
			) - 0.5;

			float star = Star(gv - offset - pad, flareSize);

			float twinkle = trisn(u_time * u_speed + seed * 6.2831) * 0.5 + 1.0;
			twinkle = mix(1.0, twinkle, u_twinkle_intensity);
			star *= twinkle;
			
			col += star * size * starColor;
		}
	}

	return col;
}

void main() {
	vec2 focalPx = vec2(u_focal_x, u_focal_y) * u_resolution.xy;
	vec2 uv = (v_uv * u_resolution.xy - focalPx) / u_resolution.y;

	float autoRotAngle = u_time * u_rotation_speed;
	mat2 autoRot = mat2(cos(autoRotAngle), -sin(autoRotAngle), sin(autoRotAngle), cos(autoRotAngle));
	uv = autoRot * uv;

	uv = mat2(u_rotation_x, -u_rotation_y, u_rotation_y, u_rotation_x) * uv;

	vec3 col = vec3(0.0);

	for (float i = 0.0; i < 1.0; i += 1.0 / NUM_LAYER) {
		float depth = fract(i + u_star_speed * u_speed);
		float scale = mix(20.0 * u_density, 0.5 * u_density, depth);
		float fade = depth * smoothstep(1.0, 0.9, depth);
		col += StarLayer(uv * scale + i * 453.32) * fade;
	}

	fragColor = vec4(col, 1.0);
}`

	function createShader(context: WebGL2RenderingContext, type: GLShaderType, source: string) {
		const shader = context.createShader(type)
		if (!shader) {
			throw new Error('Failed to create shader')
		}
		context.shaderSource(shader, source)
		context.compileShader(shader)
		if (!context.getShaderParameter(shader, context.COMPILE_STATUS)) {
			const info = context.getShaderInfoLog(shader)
			context.deleteShader(shader)
			throw new Error(`Shader compile error: ${info ?? 'unknown'}`)
		}
		return shader
	}

	function initWebGL() {
		gl = canvasRef.getContext('webgl2', {
			alpha: true,
			premultipliedAlpha: false,
			preserveDrawingBuffer: true,
		})

		if (!gl) {
			throw new Error('WebGL2 context not available; cannot render galaxy background')
		}

		const vertexShader = createShader(gl, gl.VERTEX_SHADER, vertexShaderSource)
		const fragmentShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource)

		program = gl.createProgram()
		if (!program) {
			throw new Error('Failed to create WebGL program')
		}
		gl.attachShader(program, vertexShader)
		gl.attachShader(program, fragmentShader)
		gl.linkProgram(program)
		if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
			const info = gl.getProgramInfoLog(program) ?? 'unknown'
			throw new Error(`Program link error: ${info}`)
		}

		const vertices = new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1])
		const buffer = gl.createBuffer()
		if (!buffer) {
			throw new Error('Failed to create vertex buffer')
		}
		gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
		gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW)

		const positionLoc = gl.getAttribLocation(program, 'a_position')
		gl.enableVertexAttribArray(positionLoc)
		gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0)

		gl.clearColor(0, 0, 0, 1)
	}

	function resize(width: number, height: number) {
		if (!gl || !canvasRef) return
		const dpr = window.devicePixelRatio || 1
		const displayWidth = Math.max(1, Math.floor(width * dpr))
		const displayHeight = Math.max(1, Math.floor(height * dpr))

		if (canvasRef.width !== displayWidth || canvasRef.height !== displayHeight) {
			canvasRef.width = displayWidth
			canvasRef.height = displayHeight
			canvasRef.style.width = `${width}px`
			canvasRef.style.height = `${height}px`
			gl.viewport(0, 0, displayWidth, displayHeight)
		}
	}

	function animate(time: number) {
		if (!gl || !program) return

		gl.useProgram(program)

		const seconds = time * 0.001

		// Configuration matching the inspiration
		const focal = [0.5, 0.5]
		const rotation = [1.0, 0.0]
		const starSpeed = 0.5
		const density = 1.0
		const speed = 1.0
		const glowIntensity = 0.3
		const twinkleIntensity = 0.3
		const rotationSpeed = 0.1

		gl.uniform1f(gl.getUniformLocation(program, 'u_time'), seconds)
		gl.uniform2f(
			gl.getUniformLocation(program, 'u_resolution'),
			canvasRef.width,
			canvasRef.height
		)
		gl.uniform1f(gl.getUniformLocation(program, 'u_focal_x'), focal[0])
		gl.uniform1f(gl.getUniformLocation(program, 'u_focal_y'), focal[1])
		gl.uniform1f(gl.getUniformLocation(program, 'u_rotation_x'), rotation[0])
		gl.uniform1f(gl.getUniformLocation(program, 'u_rotation_y'), rotation[1])
		gl.uniform1f(gl.getUniformLocation(program, 'u_star_speed'), (seconds * starSpeed) / 10.0)
		gl.uniform1f(gl.getUniformLocation(program, 'u_density'), density)
		gl.uniform1f(gl.getUniformLocation(program, 'u_speed'), speed)
		gl.uniform1f(gl.getUniformLocation(program, 'u_glow_intensity'), glowIntensity)
		gl.uniform1f(gl.getUniformLocation(program, 'u_twinkle_intensity'), twinkleIntensity)
		gl.uniform1f(gl.getUniformLocation(program, 'u_rotation_speed'), rotationSpeed)

		gl.clear(gl.COLOR_BUFFER_BIT)
		gl.drawArrays(gl.TRIANGLES, 0, 6)
		gl.flush()

		animationId = requestAnimationFrame(animate)
	}

	onMount(() => {
		try {
			initWebGL()

			resizeObserver = new ResizeObserver((entries) => {
				for (const entry of entries) {
					const box = entry.contentRect
					resize(box.width, box.height)
				}
			})

			if (containerRef) {
				resizeObserver.observe(containerRef)
			}

			const rect = containerRef.getBoundingClientRect()
			resize(rect.width, rect.height)
			animationId = requestAnimationFrame(animate)
		} catch (error) {
			console.error('Failed to initialize WebGL galaxy background:', error)
		}
	})

	onDestroy(() => {
		if (animationId !== null) {
			cancelAnimationFrame(animationId)
		}
		resizeObserver?.disconnect()
		if (gl) {
			gl.getExtension('WEBGL_lose_context')?.loseContext()
		}
	})
</script>

<div class="webgl-galaxy" bind:this={containerRef}>
	<canvas bind:this={canvasRef}></canvas>

	<!-- Slotted content rendered on top of galaxy -->
	<div class="content-layer">
		{@render children?.()}
	</div>
</div>

<style>
	.webgl-galaxy {
		position: absolute;
		inset: 0;
		overflow: hidden;
	}

	canvas {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		display: block;
		pointer-events: none;
	}

	.content-layer {
		position: relative;
		width: 100%;
		height: 100%;
		z-index: 1;
	}
</style>
