<script lang="ts">
    import { setBackgroundContext } from '$lib/contexts/backgroundContext'
    import type { Snippet } from 'svelte'
    import { onDestroy, onMount } from 'svelte'

    interface Props {
        children?: Snippet
        rotation?: number
        speed?: number
        colors?: string[]
        transparent?: boolean
        autoRotate?: number
        scale?: number
        frequency?: number
        warpStrength?: number
        mouseInfluence?: number
        parallax?: number
        noise?: number
    }

    let {
        children,
        rotation = 45,
        speed = 0.2,
        colors = [],
        transparent = true,
        autoRotate = 0,
        scale = 1,
        frequency = 1,
        warpStrength = 1,
        mouseInfluence = 1,
        parallax = 0.5,
        noise = 0.1,
    }: Props = $props()

    const MAX_COLORS = 8

    let containerRef: HTMLDivElement
    let canvasRef: HTMLCanvasElement
    let gl: WebGL2RenderingContext | null = null
    let program: WebGLProgram | null = null
    let animationId: number | null = null
    let resizeObserver: ResizeObserver | null = null
    let startTime = 0
    let subscribers: Array<() => void> = []
    let pointerTarget = { x: 0, y: 0 }
    let pointerCurrent = { x: 0, y: 0 }
    let pointerSmooth = 8

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

void main() {
	vUv = a_position * 0.5 + 0.5;
	gl_Position = vec4(a_position, 0.0, 1.0);
}`

    const fragmentShaderSource = `#version 300 es
precision highp float;

#define MAX_COLORS ${MAX_COLORS}

uniform vec2 uCanvas;
uniform float uTime;
uniform float uSpeed;
uniform vec2 uRot;
uniform int uColorCount;
uniform vec3 uColors[MAX_COLORS];
uniform int uTransparent;
uniform float uScale;
uniform float uFrequency;
uniform float uWarpStrength;
uniform vec2 uPointer;
uniform float uMouseInfluence;
uniform float uParallax;
uniform float uNoise;

in vec2 vUv;
out vec4 fragColor;

void main() {
	float t = uTime * uSpeed;
	vec2 p = vUv * 2.0 - 1.0;
	p += uPointer * uParallax * 0.1;
	vec2 rp = vec2(p.x * uRot.x - p.y * uRot.y, p.x * uRot.y + p.y * uRot.x);
	vec2 q = vec2(rp.x * (uCanvas.x / uCanvas.y), rp.y);
	q /= max(uScale, 0.0001);
	q /= 0.5 + 0.2 * dot(q, q);
	q += 0.2 * cos(t) - 7.56;
	vec2 toward = (uPointer - rp);
	q += toward * uMouseInfluence * 0.2;

	vec3 col = vec3(0.0);
	float a = 1.0;

	if (uColorCount > 0) {
		vec2 s = q;
		vec3 sumCol = vec3(0.0);
		float cover = 0.0;
		for (int i = 0; i < MAX_COLORS; ++i) {
			if (i >= uColorCount) break;
			s -= 0.01;
			vec2 r = sin(1.5 * (s.yx * uFrequency) + 2.0 * cos(s * uFrequency));
			float m0 = length(r + sin(5.0 * r.y * uFrequency - 3.0 * t + float(i)) / 4.0);
			float kBelow = clamp(uWarpStrength, 0.0, 1.0);
			float kMix = pow(kBelow, 0.3);
			float gain = 1.0 + max(uWarpStrength - 1.0, 0.0);
			vec2 disp = (r - s) * kBelow;
			vec2 warped = s + disp * gain;
			float m1 = length(warped + sin(5.0 * warped.y * uFrequency - 3.0 * t + float(i)) / 4.0);
			float m = mix(m0, m1, kMix);
			float w = 1.0 - exp(-6.0 / exp(6.0 * m));
			sumCol += uColors[i] * w;
			cover = max(cover, w);
		}
		col = clamp(sumCol, 0.0, 1.0);
		a = uTransparent > 0 ? cover : 1.0;
	} else {
		vec2 s = q;
		for (int k = 0; k < 3; ++k) {
			s -= 0.01;
			vec2 r = sin(1.5 * (s.yx * uFrequency) + 2.0 * cos(s * uFrequency));
			float m0 = length(r + sin(5.0 * r.y * uFrequency - 3.0 * t + float(k)) / 4.0);
			float kBelow = clamp(uWarpStrength, 0.0, 1.0);
			float kMix = pow(kBelow, 0.3);
			float gain = 1.0 + max(uWarpStrength - 1.0, 0.0);
			vec2 disp = (r - s) * kBelow;
			vec2 warped = s + disp * gain;
			float m1 = length(warped + sin(5.0 * warped.y * uFrequency - 3.0 * t + float(k)) / 4.0);
			float m = mix(m0, m1, kMix);
			col[k] = 1.0 - exp(-6.0 / exp(6.0 * m));
		}
		a = uTransparent > 0 ? max(max(col.r, col.g), col.b) : 1.0;
	}

	if (uNoise > 0.0001) {
		float n = fract(sin(dot(gl_FragCoord.xy + vec2(uTime), vec2(12.9898, 78.233))) * 43758.5453123);
		col += (n - 0.5) * uNoise;
		col = clamp(col, 0.0, 1.0);
	}

	vec3 rgb = (uTransparent > 0) ? col * a : col;
	fragColor = vec4(rgb, a);
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
        const h = hex.replace('#', '').trim()
        const v =
            h.length === 3
                ? [parseInt(h[0] + h[0], 16), parseInt(h[1] + h[1], 16), parseInt(h[2] + h[2], 16)]
                : [
                      parseInt(h.slice(0, 2), 16),
                      parseInt(h.slice(2, 4), 16),
                      parseInt(h.slice(4, 6), 16),
                  ]
        return { r: v[0] / 255, g: v[1] / 255, b: v[2] / 255 }
    }

    function resize() {
        if (!canvasRef || !containerRef || !gl || !program) return

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

        // Smooth pointer lerp
        const dt = 1 / 60 // approximate
        const amt = Math.min(1, dt * pointerSmooth)
        pointerCurrent.x += (pointerTarget.x - pointerCurrent.x) * amt
        pointerCurrent.y += (pointerTarget.y - pointerCurrent.y) * amt

        gl.clearColor(0, 0, 0, transparent ? 0 : 1)
        gl.clear(gl.COLOR_BUFFER_BIT)

        gl.useProgram(program)

        // Update canvas uniform
        const rect = containerRef.getBoundingClientRect()
        const uCanvas = gl.getUniformLocation(program, 'uCanvas')
        gl.uniform2f(uCanvas, rect.width, rect.height)

        // Set uniforms
        const uTime = gl.getUniformLocation(program, 'uTime')
        const uSpeed = gl.getUniformLocation(program, 'uSpeed')
        const uRot = gl.getUniformLocation(program, 'uRot')
        const uColorCount = gl.getUniformLocation(program, 'uColorCount')
        const uTransparent = gl.getUniformLocation(program, 'uTransparent')
        const uScale = gl.getUniformLocation(program, 'uScale')
        const uFrequency = gl.getUniformLocation(program, 'uFrequency')
        const uWarpStrength = gl.getUniformLocation(program, 'uWarpStrength')
        const uPointer = gl.getUniformLocation(program, 'uPointer')
        const uMouseInfluence = gl.getUniformLocation(program, 'uMouseInfluence')
        const uParallax = gl.getUniformLocation(program, 'uParallax')
        const uNoise = gl.getUniformLocation(program, 'uNoise')

        gl.uniform1f(uTime, elapsed)
        gl.uniform1f(uSpeed, speed)
        gl.uniform1f(uScale, scale)
        gl.uniform1f(uFrequency, frequency)
        gl.uniform1f(uWarpStrength, warpStrength)
        gl.uniform1f(uMouseInfluence, mouseInfluence)
        gl.uniform1f(uParallax, parallax)
        gl.uniform1f(uNoise, noise)

        // Rotation
        const deg = (rotation % 360) + autoRotate * elapsed
        const rad = (deg * Math.PI) / 180
        const c = Math.cos(rad)
        const s = Math.sin(rad)
        gl.uniform2f(uRot, c, s)

        // Pointer
        gl.uniform2f(uPointer, pointerCurrent.x, pointerCurrent.y)

        // Colors
        const colorArray = colors.filter(Boolean).slice(0, MAX_COLORS)
        const rgbColors = colorArray.map(hexToRgb)
        const flatColors = new Float32Array(MAX_COLORS * 3)
        for (let i = 0; i < MAX_COLORS; i++) {
            if (i < rgbColors.length) {
                flatColors[i * 3] = rgbColors[i].r
                flatColors[i * 3 + 1] = rgbColors[i].g
                flatColors[i * 3 + 2] = rgbColors[i].b
            } else {
                flatColors[i * 3] = 0
                flatColors[i * 3 + 1] = 0
                flatColors[i * 3 + 2] = 0
            }
        }
        const uColors = gl.getUniformLocation(program, 'uColors')
        gl.uniform3fv(uColors, flatColors)
        gl.uniform1i(uColorCount, colorArray.length)
        gl.uniform1i(uTransparent, transparent ? 1 : 0)

        gl.drawArrays(gl.TRIANGLES, 0, 6)

        animationId = requestAnimationFrame(animate)
    }

    function handlePointerMove(e: PointerEvent) {
        if (!containerRef) return
        const rect = containerRef.getBoundingClientRect()
        const x = ((e.clientX - rect.left) / (rect.width || 1)) * 2 - 1
        const y = -(((e.clientY - rect.top) / (rect.height || 1)) * 2 - 1)
        pointerTarget.x = x
        pointerTarget.y = y
    }

    onMount(() => {
        const context = canvasRef.getContext('webgl2', { alpha: true, premultipliedAlpha: true })
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

        // Enable blending for transparency
        gl.enable(gl.BLEND)
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)

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

        // Add pointer event listener
        containerRef.addEventListener('pointermove', handlePointerMove)

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

        if (containerRef) {
            containerRef.removeEventListener('pointermove', handlePointerMove)
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
