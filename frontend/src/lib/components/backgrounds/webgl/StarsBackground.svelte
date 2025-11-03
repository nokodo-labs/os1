<script lang="ts">
    import { onDestroy, onMount } from 'svelte'

    let containerRef: HTMLDivElement
    let canvasRef: HTMLCanvasElement
    let gl: WebGL2RenderingContext | null = null
    let program: WebGLProgram | null = null
    let animationId: number | null = null
    let resizeObserver: ResizeObserver | null = null
    let pointerTarget = { x: 0.5, y: 0.5 }
    let pointerSmooth = { x: 0.5, y: 0.5 }

    const vertexShaderSource = `#version 300 es
in vec2 a_position;
out vec2 v_uv;

void main() {
	v_uv = a_position * 0.5 + 0.5;
	gl_Position = vec4(a_position, 0.0, 1.0);
}`

    const fragmentShaderSource = `#version 300 es
precision highp float;


out vec4 fragColor;

uniform float u_time;
uniform vec2 u_resolution;
uniform vec2 u_pointer;
uniform float u_density;
uniform float u_glow;
uniform float u_saturation;
uniform float u_twinkle;
uniform float u_rotation;
uniform float u_hue_shift;

const float LAYERS = 4.0;
const mat2 ROT_MAT = mat2(0.70710678, -0.70710678, 0.70710678, 0.70710678);

float hash21(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

vec3 hsv2rgb(vec3 c) {
	vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
	vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
	return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

float star(vec2 uv, float flare) {
	float d = length(uv);
	float inv = 0.035 * u_glow / (d + 0.0008);
	float streaks = pow(max(0.0, 1.0 - abs(uv.x * uv.y) * 320.0), 4.0);
	vec2 rUv = ROT_MAT * uv;
	float cross = pow(max(0.0, 1.0 - abs(rUv.x * rUv.y) * 320.0), 4.0);
	float glow = inv + (streaks + cross) * flare * 0.5 * u_glow;
	return glow * smoothstep(0.65, 0.05, d);
}

vec3 starLayer(vec2 uv, float depth) {
	vec3 color = vec3(0.0);
	vec2 gv = fract(uv) - 0.5;
	vec2 id = floor(uv);

	for (int y = -1; y <= 1; ++y) {
		for (int x = -1; x <= 1; ++x) {
			vec2 offset = vec2(float(x), float(y));
			vec2 cell = id + offset;
			float seed = hash21(cell);
			float size = smoothstep(0.55, 0.98, fract(seed * 345.32));
			if (size < 0.001) {
				continue;
			}

			vec2 jitter = vec2(hash21(cell + 11.1), hash21(cell + 27.7)) - 0.5;
			vec2 starPos = gv - offset + jitter;

			float flare = mix(0.25, 1.0, size);
			float sparkle = sin(u_time * (0.4 + depth) + seed * 6.28318) * 0.5 + 0.5;
			sparkle = mix(1.0, sparkle, u_twinkle);

			float m = star(starPos, flare) * size * sparkle;

			float hue = fract(u_hue_shift + seed * 0.25 + depth * 0.05);
			float sat = mix(0.35, 0.8, depth) * u_saturation;
			vec3 starColor = hsv2rgb(vec3(hue, sat, 1.0));
			color += starColor * m;
		}
	}

	return color;
}

void main() {
	vec2 resolution = u_resolution;
	vec2 centered = (v_uv * resolution - 0.5 * resolution) / min(resolution.x, resolution.y);

	float rot = u_rotation;
	float c = cos(rot);
	float s = sin(rot);
	centered = mat2(c, -s, s, c) * centered;

	vec2 parallax = (u_pointer - 0.5) * 0.25;
	centered += parallax;

	vec3 accum = vec3(0.0);

	for (float i = 0.0; i < LAYERS; i += 1.0) {
		float depth = i / LAYERS;
		float scale = mix(26.0 * u_density, 2.2 * u_density, depth);
		float drift = mix(0.018, 0.065, depth);

		vec2 layerUv = centered * scale;
		layerUv.x += sin(u_time * 0.12 + depth * 4.6) * 0.08;
		layerUv.y += u_time * drift;
		layerUv += i * 37.271;

		accum += starLayer(layerUv, depth) * mix(1.25, 0.65, depth);
	}

	float radius = length(centered);
	float vignette = smoothstep(1.25, 0.15, radius);
	accum *= vignette;

	vec3 nebulaHue = hsv2rgb(vec3(u_hue_shift + 0.08, 0.35 * u_saturation, 0.4));
	float nebula = smoothstep(0.75, 0.0, length(centered - vec2(0.25, 0.12))) * 0.35;
	nebula += smoothstep(1.1, 0.25, length(centered + vec2(0.18, 0.28))) * 0.22;
	accum += nebulaHue * nebula;

	accum = pow(accum, vec3(0.92));

	fragColor = vec4(accum, 1.0);
}`

    function createShader(context: WebGL2RenderingContext, type: GLenum, source: string) {
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

        pointerSmooth.x += (pointerTarget.x - pointerSmooth.x) * 0.045
        pointerSmooth.y += (pointerTarget.y - pointerSmooth.y) * 0.045

        const seconds = time * 0.001
        const width = canvasRef.width
        const height = canvasRef.height

        const timeLoc = gl.getUniformLocation(program, 'u_time')
        const resolutionLoc = gl.getUniformLocation(program, 'u_resolution')
        const pointerLoc = gl.getUniformLocation(program, 'u_pointer')
        const densityLoc = gl.getUniformLocation(program, 'u_density')
        const glowLoc = gl.getUniformLocation(program, 'u_glow')
        const saturationLoc = gl.getUniformLocation(program, 'u_saturation')
        const twinkleLoc = gl.getUniformLocation(program, 'u_twinkle')
        const rotationLoc = gl.getUniformLocation(program, 'u_rotation')
        const hueShiftLoc = gl.getUniformLocation(program, 'u_hue_shift')

        gl.uniform1f(timeLoc, seconds)
        gl.uniform2f(resolutionLoc, width, height)
        gl.uniform2f(pointerLoc, pointerSmooth.x, pointerSmooth.y)
        gl.uniform1f(densityLoc, 1.0)
        gl.uniform1f(glowLoc, 1.0)
        gl.uniform1f(saturationLoc, 1.0)
        gl.uniform1f(twinkleLoc, 0.7)
        gl.uniform1f(rotationLoc, seconds * 0.04)
        gl.uniform1f(hueShiftLoc, 0.58)

        gl.clear(gl.COLOR_BUFFER_BIT)
        gl.drawArrays(gl.TRIANGLES, 0, 6)

        animationId = requestAnimationFrame(animate)
    }

    function handlePointerMove(event: PointerEvent) {
        if (!containerRef) return
        const rect = containerRef.getBoundingClientRect()
        pointerTarget = {
            x: (event.clientX - rect.left) / rect.width,
            y: 1 - (event.clientY - rect.top) / rect.height,
        }
    }

    function handlePointerLeave() {
        pointerTarget = { x: 0.5, y: 0.5 }
    }

    onMount(() => {
        initWebGL()

        resizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                const box = entry.contentRect
                resize(box.width, box.height)
            }
        })

        if (containerRef) {
            resizeObserver.observe(containerRef)
            containerRef.addEventListener('pointermove', handlePointerMove)
            containerRef.addEventListener('pointerleave', handlePointerLeave)
        }

        const rect = containerRef.getBoundingClientRect()
        resize(rect.width, rect.height)
        animationId = requestAnimationFrame(animate)
    })

    onDestroy(() => {
        if (animationId !== null) {
            cancelAnimationFrame(animationId)
        }
        resizeObserver?.disconnect()
        containerRef?.removeEventListener('pointermove', handlePointerMove)
        containerRef?.removeEventListener('pointerleave', handlePointerLeave)
        if (gl) {
            gl.getExtension('WEBGL_lose_context')?.loseContext()
        }
    })
</script>

<div class="stars-background" bind:this={containerRef}>
    <canvas bind:this={canvasRef}></canvas>
</div>

<style>
    .stars-background {
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
    }
</style>
