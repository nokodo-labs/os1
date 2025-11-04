<script lang="ts">
    import { setBackgroundContext } from '$lib/contexts/backgroundContext'
    import type { Snippet } from 'svelte'
    import { onDestroy, onMount } from 'svelte'

    export type RaysOrigin =
        | 'top-center'
        | 'top-left'
        | 'top-right'
        | 'right'
        | 'left'
        | 'bottom-center'
        | 'bottom-right'
        | 'bottom-left'

    interface Props {
        children?: Snippet
        raysOrigin?: RaysOrigin
        raysColor?: string
        raysSpeed?: number
        lightSpread?: number
        rayLength?: number
        pulsating?: boolean
        fadeDistance?: number
        saturation?: number
        followMouse?: boolean
        mouseInfluence?: number
        noiseAmount?: number
        distortion?: number
    }

    let {
        children,
        raysOrigin = 'top-center',
        raysColor = '#ffffff',
        raysSpeed = 1,
        lightSpread = 1,
        rayLength = 2,
        pulsating = false,
        fadeDistance = 1.0,
        saturation = 1.0,
        followMouse = true,
        mouseInfluence = 0.1,
        noiseAmount = 0.0,
        distortion = 0.0,
    }: Props = $props()

    let containerRef: HTMLDivElement
    let canvasRef: HTMLCanvasElement
    let gl: WebGL2RenderingContext | null = null
    let program: WebGLProgram | null = null
    let animationId: number | null = null
    let resizeObserver: ResizeObserver | null = null
    let startTime = 0
    let subscribers: Array<() => void> = []
    let mouseRef = { x: 0.5, y: 0.5 }
    let smoothMouseRef = { x: 0.5, y: 0.5 }

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

uniform float iTime;
uniform vec2 iResolution;
uniform vec2 rayPos;
uniform vec2 rayDir;
uniform vec3 raysColor;
uniform float raysSpeed;
uniform float lightSpread;
uniform float rayLength;
uniform float pulsating;
uniform float fadeDistance;
uniform float saturation;
uniform vec2 mousePos;
uniform float mouseInfluence;
uniform float noiseAmount;
uniform float distortion;

in vec2 vUv;
out vec4 fragColor;

float noise(vec2 st) {
	return fract(sin(dot(st.xy, vec2(12.9898,78.233))) * 43758.5453123);
}

float rayStrength(vec2 raySource, vec2 rayRefDirection, vec2 coord,
                  float seedA, float seedB, float speed) {
	vec2 sourceToCoord = coord - raySource;
	vec2 dirNorm = normalize(sourceToCoord);
	float cosAngle = dot(dirNorm, rayRefDirection);

	float distortedAngle = cosAngle + distortion * sin(iTime * 2.0 + length(sourceToCoord) * 0.01) * 0.2;
	
	float spreadFactor = pow(max(distortedAngle, 0.0), 1.0 / max(lightSpread, 0.001));

	float distance = length(sourceToCoord);
	float maxDistance = iResolution.x * rayLength;
	float lengthFalloff = clamp((maxDistance - distance) / maxDistance, 0.0, 1.0);
	
	float fadeFalloff = clamp((iResolution.x * fadeDistance - distance) / (iResolution.x * fadeDistance), 0.5, 1.0);
	float pulse = pulsating > 0.5 ? (0.8 + 0.2 * sin(iTime * speed * 3.0)) : 1.0;

	float baseStrength = clamp(
		(0.45 + 0.15 * sin(distortedAngle * seedA + iTime * speed)) +
		(0.3 + 0.2 * cos(-distortedAngle * seedB + iTime * speed)),
		0.0, 1.0
	);

	return baseStrength * lengthFalloff * fadeFalloff * spreadFactor * pulse;
}

void mainImage(out vec4 color, in vec2 fragCoord) {
	vec2 coord = vec2(fragCoord.x, iResolution.y - fragCoord.y);
	
	vec2 finalRayDir = rayDir;
	if (mouseInfluence > 0.0) {
		vec2 mouseScreenPos = mousePos * iResolution.xy;
		vec2 mouseDirection = normalize(mouseScreenPos - rayPos);
		finalRayDir = normalize(mix(rayDir, mouseDirection, mouseInfluence));
	}

	vec4 rays1 = vec4(1.0) *
	             rayStrength(rayPos, finalRayDir, coord, 36.2214, 21.11349,
	                         1.5 * raysSpeed);
	vec4 rays2 = vec4(1.0) *
	             rayStrength(rayPos, finalRayDir, coord, 22.3991, 18.0234,
	                         1.1 * raysSpeed);

	color = rays1 * 0.5 + rays2 * 0.4;

	if (noiseAmount > 0.0) {
		float n = noise(coord * 0.01 + iTime * 0.1);
		color.rgb *= (1.0 - noiseAmount + noiseAmount * n);
	}

	float brightness = 1.0 - (coord.y / iResolution.y);
	color.x *= 0.1 + brightness * 0.8;
	color.y *= 0.3 + brightness * 0.6;
	color.z *= 0.5 + brightness * 0.5;

	if (saturation != 1.0) {
		float gray = dot(color.rgb, vec3(0.299, 0.587, 0.114));
		color.rgb = mix(vec3(gray), color.rgb, saturation);
	}

	color.rgb *= raysColor;
}

void main() {
	vec4 color;
	mainImage(color, gl_FragCoord.xy);
	fragColor = color;
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
        const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
        return m
            ? {
                  r: parseInt(m[1], 16) / 255,
                  g: parseInt(m[2], 16) / 255,
                  b: parseInt(m[3], 16) / 255,
              }
            : { r: 1, g: 1, b: 1 }
    }

    function getAnchorAndDir(
        origin: RaysOrigin,
        w: number,
        h: number
    ): { anchor: [number, number]; dir: [number, number] } {
        const outside = 0.2
        switch (origin) {
            case 'top-left':
                return { anchor: [0, -outside * h], dir: [0, 1] }
            case 'top-right':
                return { anchor: [w, -outside * h], dir: [0, 1] }
            case 'left':
                return { anchor: [-outside * w, 0.5 * h], dir: [1, 0] }
            case 'right':
                return { anchor: [(1 + outside) * w, 0.5 * h], dir: [-1, 0] }
            case 'bottom-left':
                return { anchor: [0, (1 + outside) * h], dir: [0, -1] }
            case 'bottom-center':
                return { anchor: [0.5 * w, (1 + outside) * h], dir: [0, -1] }
            case 'bottom-right':
                return { anchor: [w, (1 + outside) * h], dir: [0, -1] }
            default: // "top-center"
                return { anchor: [0.5 * w, -outside * h], dir: [0, 1] }
        }
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

        // Smooth mouse lerp
        const smoothing = 0.92
        smoothMouseRef.x = smoothMouseRef.x * smoothing + mouseRef.x * (1 - smoothing)
        smoothMouseRef.y = smoothMouseRef.y * smoothing + mouseRef.y * (1 - smoothing)

        gl.clearColor(0, 0, 0, 0)
        gl.clear(gl.COLOR_BUFFER_BIT)

        gl.useProgram(program)

        // Update resolution and ray uniforms
        const dpr = Math.min(window.devicePixelRatio, 2)
        const rect = containerRef.getBoundingClientRect()
        const width = Math.floor(rect.width * dpr)
        const height = Math.floor(rect.height * dpr)

        const iResolution = gl.getUniformLocation(program, 'iResolution')
        gl.uniform2f(iResolution, width, height)

        const { anchor, dir } = getAnchorAndDir(raysOrigin, width, height)
        const rayPos = gl.getUniformLocation(program, 'rayPos')
        const rayDir = gl.getUniformLocation(program, 'rayDir')
        gl.uniform2f(rayPos, anchor[0], anchor[1])
        gl.uniform2f(rayDir, dir[0], dir[1])

        // Set uniforms
        const iTime = gl.getUniformLocation(program, 'iTime')
        const raysColorLoc = gl.getUniformLocation(program, 'raysColor')
        const raysSpeedLoc = gl.getUniformLocation(program, 'raysSpeed')
        const lightSpreadLoc = gl.getUniformLocation(program, 'lightSpread')
        const rayLengthLoc = gl.getUniformLocation(program, 'rayLength')
        const pulsatingLoc = gl.getUniformLocation(program, 'pulsating')
        const fadeDistanceLoc = gl.getUniformLocation(program, 'fadeDistance')
        const saturationLoc = gl.getUniformLocation(program, 'saturation')
        const mousePosLoc = gl.getUniformLocation(program, 'mousePos')
        const mouseInfluenceLoc = gl.getUniformLocation(program, 'mouseInfluence')
        const noiseAmountLoc = gl.getUniformLocation(program, 'noiseAmount')
        const distortionLoc = gl.getUniformLocation(program, 'distortion')

        gl.uniform1f(iTime, elapsed)
        gl.uniform1f(raysSpeedLoc, raysSpeed)
        gl.uniform1f(lightSpreadLoc, lightSpread)
        gl.uniform1f(rayLengthLoc, rayLength)
        gl.uniform1f(pulsatingLoc, pulsating ? 1.0 : 0.0)
        gl.uniform1f(fadeDistanceLoc, fadeDistance)
        gl.uniform1f(saturationLoc, saturation)
        gl.uniform1f(mouseInfluenceLoc, mouseInfluence)
        gl.uniform1f(noiseAmountLoc, noiseAmount)
        gl.uniform1f(distortionLoc, distortion)

        const rgb = hexToRgb(raysColor)
        gl.uniform3f(raysColorLoc, rgb.r, rgb.g, rgb.b)

        if (followMouse && mouseInfluence > 0.0) {
            gl.uniform2f(mousePosLoc, smoothMouseRef.x, smoothMouseRef.y)
        } else {
            gl.uniform2f(mousePosLoc, 0.5, 0.5)
        }

        gl.drawArrays(gl.TRIANGLES, 0, 6)

        animationId = requestAnimationFrame(animate)
    }

    function handleMouseMove(e: MouseEvent) {
        if (!containerRef) return
        const rect = containerRef.getBoundingClientRect()
        const x = (e.clientX - rect.left) / rect.width
        const y = (e.clientY - rect.top) / rect.height
        mouseRef.x = x
        mouseRef.y = y
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

        // Add mouse event listener
        if (followMouse) {
            window.addEventListener('mousemove', handleMouseMove)
        }

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

        if (followMouse) {
            window.removeEventListener('mousemove', handleMouseMove)
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
