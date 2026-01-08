<script lang="ts">
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { getBackgroundContext } from '$lib/contexts/backgroundContext'
	import type { Snippet } from 'svelte'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
		role: 'user' | 'assistant'
		content: string
		timestamp?: Date
		actions?: Snippet
	}

	let { role, content, timestamp, actions }: Props = $props()
	const isUser = $derived(role === 'user')

	type GLShaderType =
		| WebGL2RenderingContext['VERTEX_SHADER']
		| WebGL2RenderingContext['FRAGMENT_SHADER']

	let canvasRef: HTMLCanvasElement
	let containerRef: HTMLDivElement
	let gl: WebGL2RenderingContext | null = null
	let program: WebGLProgram | null = null
	let animationId: number | null = null
	let startTime = 0
	let backgroundTexture: WebGLTexture | null = null
	let backgroundCanvas: HTMLCanvasElement | null = null

	const backgroundContext = getBackgroundContext()

	const vertexShaderSource = `#version 300 es
in vec2 a_position;
out vec2 vUv;

void main() {
    vUv = 0.5 * (a_position + 1.0);
    gl_Position = vec4(a_position, 0.0, 1.0);
}`

	const fragmentShaderSource = `#version 300 es
precision highp float;

in vec2 vUv;
out vec4 fragColor;

uniform float u_time;
uniform vec2 u_resolution;
uniform vec2 u_size;
uniform vec2 u_position;  // Element position on screen
uniform vec2 u_screenSize;  // Full screen size
uniform sampler2D u_background;
uniform float u_dpr;

float roundedBox(vec2 uv, vec2 center, vec2 size, float radius) {
    vec2 q = abs(uv - center) - size + radius;
    return length(max(q, 0.0)) - radius;
}

vec3 blurBackground(vec2 uv, vec2 resolution) {
    vec3 result = vec3(0.0);
    float total = 0.0;
    float radius = 3.0;
    for (int x = -3; x <= 3; x++) {
        for (int y = -3; y <= 3; y++) {
            vec2 offset = vec2(float(x), float(y)) * 2.0 / resolution;
            float weight = exp(-(float(x * x + y * y)) / (2.0 * radius));
            result += texture(u_background, uv + offset).rgb * weight;
            total += weight;
        }
    }
    return result / total;
}

float roundedBoxSDF(vec2 p, vec2 b, float r) {
    vec2 d = abs(p) - b + vec2(r);
    return length(max(d, 0.0)) - r;
}

vec2 getNormal(vec2 uv, vec2 center, vec2 size, float radius) {
    vec2 eps = vec2(1.0) / u_resolution * 2.0;
    vec2 p = uv - center;

    float dx = (roundedBoxSDF(p + vec2(eps.x, 0.0), size, radius) - roundedBoxSDF(p - vec2(eps.x, 0.0), size, radius)) * 0.5;
    float dy = (roundedBoxSDF(p + vec2(0.0, eps.y), size, radius) - roundedBoxSDF(p - vec2(0.0, eps.y), size, radius)) * 0.5;

    vec2 gradient = vec2(dx, dy);

    float dxy1 = roundedBoxSDF(p + eps, size, radius);
    float dxy2 = roundedBoxSDF(p - eps, size, radius);
    vec2 diag = vec2(dxy1 - dxy2);

    gradient = mix(gradient, diag, 0.25);

    if (length(gradient) < 0.001) {
        return vec2(0.0);
    }
    return normalize(gradient);
}

void main() {
    // Get pixel position within element (CSS pixels)
    vec2 pixelUV = (vUv * u_resolution) / u_dpr;
    vec2 center = u_size * 0.5;
    vec2 size = u_size * 0.5;

    // Convert to screen coordinates (CSS pixels)
    vec2 screenPx = u_position + pixelUV;
    
    // Map screen coordinates to background texture UVs
    // Use screen size directly since galaxy canvas fills the viewport
    vec2 screenUV = vec2(screenPx.x / u_screenSize.x, screenPx.y / u_screenSize.y);

    vec2 local = (pixelUV - center) / size;

    float radius = 24.0;
    float dist = roundedBox(pixelUV, center, size, radius);

    if (dist > 1.0) {
        // Outside glass - show background as-is
        fragColor = texture(u_background, screenUV);
        return;
    }
    
    // DEBUG: Visualize screen UV coordinates
    // fragColor = vec4(screenUV.x, screenUV.y, 0.0, 1.0);
    // return;

    // Radial curvature refraction
    float r = clamp(length(local * 1.0), 0.0, 1.0);
    float curvature = pow(r, 1.0);
    vec2 domeNormal = normalize(local) * curvature;
    float eta = 1.0 / 1.5;
    vec2 incident = -domeNormal;
    vec2 refractVec = refract(incident, domeNormal, eta);
    vec2 curvedRefractUV = screenUV + refractVec * 0.03;

    // Edge contour refraction
    float contourFalloff = exp(-abs(dist) * 0.4);
    vec2 normal = getNormal(pixelUV, center, size, radius);
    vec2 domeNormalContour = normal * pow(contourFalloff, 1.5);
    vec2 refractVecContour = refract(vec2(0.0), domeNormalContour, eta);
    vec2 uvContour = screenUV + refractVecContour * 0.35 * contourFalloff;

    // Blend based on distance from edge and radial distance
    float edgeWeight = smoothstep(0.0, 1.0, abs(dist));
    float radialWeight = smoothstep(0.5, 1.0, r);
    float combinedWeight = clamp((edgeWeight * 1.0) + (-radialWeight * 0.5), 0.0, 1.0);
    vec2 refractUV = mix(curvedRefractUV, uvContour, combinedWeight);

    vec3 refracted = texture(u_background, refractUV).rgb;
    vec3 blurred = blurBackground(refractUV, u_screenSize * u_dpr);
    vec3 base = mix(refracted, blurred, 0.5);

    // Shadow
    float edgeFalloff = smoothstep(0.01, 0.0, dist);
    float verticalBand = 1.0 - smoothstep(-1.5, -0.2, local.y);
    float topShadow = edgeFalloff * verticalBand;
    vec3 shadowColor = vec3(0.0);
    base = mix(base, shadowColor, topShadow * 0.1);

    // Edge glow
    float edge = 1.0 - smoothstep(0.0, 0.03, dist * -2.0);
    vec3 glow = vec3(0.7);
    vec3 color = mix(base, glow, edge * 0.5);

    // NO alpha blending - full opacity with refraction
    fragColor = vec4(color, 1.0);
}`

	function compileShader(type: GLShaderType, source: string) {
		if (!gl) throw new Error('WebGL context missing during shader compile')
		const shader = gl.createShader(type)
		if (!shader) throw new Error('Unable to allocate shader')
		gl.shaderSource(shader, source)
		gl.compileShader(shader)
		if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
			const info = gl.getShaderInfoLog(shader) ?? 'unknown'
			gl.deleteShader(shader)
			throw new Error(`Shader compile error: ${info}`)
		}
		return shader
	}

	function initWebGL() {
		gl = canvasRef.getContext('webgl2', {
			alpha: true,
			premultipliedAlpha: true,
		})

		if (!gl) {
			throw new Error('WebGL2 context not available')
		}

		const vertexShader = compileShader(gl.VERTEX_SHADER, vertexShaderSource)
		const fragmentShader = compileShader(gl.FRAGMENT_SHADER, fragmentShaderSource)

		program = gl.createProgram()
		if (!program) throw new Error('Failed to create WebGL program')
		gl.attachShader(program, vertexShader)
		gl.attachShader(program, fragmentShader)
		gl.linkProgram(program)

		if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
			const info = gl.getProgramInfoLog(program) ?? 'unknown'
			throw new Error(`Program link error: ${info}`)
		}

		const vertices = new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1])
		const buffer = gl.createBuffer()
		if (!buffer) throw new Error('Failed to create buffer')
		gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
		gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW)

		const positionLoc = gl.getAttribLocation(program, 'a_position')
		gl.enableVertexAttribArray(positionLoc)
		gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0)

		gl.enable(gl.BLEND)
		gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)

		// Create background texture
		backgroundTexture = gl.createTexture()
		gl.bindTexture(gl.TEXTURE_2D, backgroundTexture)
		gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true)
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)

		// Initialize with black texture
		const blackPixel = new Uint8Array([0, 0, 0, 255])
		gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, blackPixel)

		startTime = performance.now()
	}

	function resize() {
		if (!gl || !program) return
		const dpr = window.devicePixelRatio || 1
		const rect = containerRef.getBoundingClientRect()
		const width = Math.max(1, Math.floor(rect.width * dpr))
		const height = Math.max(1, Math.floor(rect.height * dpr))

		if (canvasRef.width !== width || canvasRef.height !== height) {
			canvasRef.width = width
			canvasRef.height = height
			canvasRef.style.width = `${rect.width}px`
			canvasRef.style.height = `${rect.height}px`
			gl.viewport(0, 0, width, height)
		}
	}

	function animate() {
		if (!gl || !program) return

		resize()

		if (!backgroundCanvas && backgroundContext) {
			backgroundCanvas = backgroundContext.getCanvas()
		}

		// Skip drawing until the galaxy background has been sized
		if (!backgroundCanvas || backgroundCanvas.width === 0 || backgroundCanvas.height === 0) {
			animationId = requestAnimationFrame(animate)
			return
		}

		// Update background texture from galaxy canvas
		if (backgroundTexture) {
			gl.bindTexture(gl.TEXTURE_2D, backgroundTexture)
			try {
				gl.texImage2D(
					gl.TEXTURE_2D,
					0,
					gl.RGBA,
					gl.RGBA,
					gl.UNSIGNED_BYTE,
					backgroundCanvas
				)
			} catch (e) {
				console.error('Failed to update background texture:', e)
			}
		}

		gl.useProgram(program)

		const timeLoc = gl.getUniformLocation(program, 'u_time')
		const resolutionLoc = gl.getUniformLocation(program, 'u_resolution')
		const sizeLoc = gl.getUniformLocation(program, 'u_size')
		const positionLoc = gl.getUniformLocation(program, 'u_position')
		const screenSizeLoc = gl.getUniformLocation(program, 'u_screenSize')
		const dprLoc = gl.getUniformLocation(program, 'u_dpr')
		const backgroundLoc = gl.getUniformLocation(program, 'u_background')

		const currentTime = (performance.now() - startTime) * 0.001
		const dpr = window.devicePixelRatio || 1
		const rect = containerRef.getBoundingClientRect()

		// Get element's position on screen (in CSS pixels)
		const screenX = rect.left
		const screenY = rect.top

		gl.uniform1f(timeLoc, currentTime)
		gl.uniform2f(resolutionLoc, canvasRef.width, canvasRef.height)
		gl.uniform2f(sizeLoc, rect.width, rect.height)
		gl.uniform2f(positionLoc, screenX, screenY)
		gl.uniform2f(screenSizeLoc, window.innerWidth, window.innerHeight)
		gl.uniform1f(dprLoc, dpr)
		gl.uniform1i(backgroundLoc, 0)

		gl.activeTexture(gl.TEXTURE0)
		gl.bindTexture(gl.TEXTURE_2D, backgroundTexture)

		gl.clearColor(0, 0, 0, 0)
		gl.clear(gl.COLOR_BUFFER_BIT)
		gl.drawArrays(gl.TRIANGLES, 0, 6)

		animationId = requestAnimationFrame(animate)
	}

	onMount(() => {
		// Get the galaxy background canvas
		if (backgroundContext) {
			backgroundCanvas = backgroundContext.getCanvas()
		} else {
			console.warn('No background context available')
		}

		initWebGL()
		resize()
		window.addEventListener('resize', resize)
		animationId = requestAnimationFrame(animate)
	})

	onDestroy(() => {
		if (animationId !== null) {
			cancelAnimationFrame(animationId)
		}
		window.removeEventListener('resize', resize)
		gl?.getExtension('WEBGL_lose_context')?.loseContext()
	})
</script>

<div
	class="message-container"
	class:user={isUser}
	class:assistant={!isUser}
	bind:this={containerRef}
>
	<canvas bind:this={canvasRef} class="liquid-surface"></canvas>
	<div class="message-content-wrapper">
		<div class="message-content">
			{content}
		</div>
		{#if timestamp}
			<div class="message-timestamp">
				<Timestamp {timestamp} />
			</div>
		{/if}
	</div>

	{#if actions}
		<div class="message-actions">
			{@render actions()}
		</div>
	{/if}
</div>

<style>
	.message-container {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		max-width: 80%;
		min-height: 60px;
		padding: 1rem 1.25rem;
		border-radius: 1.5rem;
		overflow: hidden;
		isolation: isolate;
		animation: messageSlideIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
	}

	@keyframes messageSlideIn {
		from {
			opacity: 0;
			transform: translateY(10px) scale(0.95);
		}
		to {
			opacity: 1;
			transform: translateY(0) scale(1);
		}
	}

	.message-container.user {
		align-self: flex-end;
	}

	.message-container.assistant {
		align-self: flex-start;
	}

	.liquid-surface {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		display: block;
		pointer-events: none;
	}

	.message-content-wrapper {
		position: relative;
		z-index: 1;
	}

	.message-content {
		color: rgba(255, 255, 255, 0.95);
		font-size: 0.95rem;
		line-height: 1.6;
		word-wrap: break-word;
	}

	.message-timestamp {
		margin-top: 0.5rem;
		font-size: 0.75rem;
		color: rgba(255, 255, 255, 0.5);
	}

	.message-actions {
		position: relative;
		z-index: 1;
		display: flex;
		gap: 0.5rem;
		padding: 0 0.5rem;
	}
</style>
