<script lang="ts">
	import { setBackgroundContext } from '$lib/contexts/backgroundContext'
	import { onDestroy, onMount, untrack, type Snippet } from 'svelte'
	import * as THREE from 'three'

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
		transparent = false,
		autoRotate = 0,
		scale = 1,
		frequency = 1,
		warpStrength = 1,
		mouseInfluence = 1,
		parallax = 0.5,
		noise = 0.1,
	}: Props = $props()

	const MAX_COLORS = 8
	const POINTER_SMOOTH = 8
	const MAX_PIXEL_RATIO = 2

	let containerRef: HTMLDivElement | null = null
	let renderer: THREE.WebGLRenderer | null = null
	let scene: THREE.Scene | null = null
	let camera: THREE.OrthographicCamera | null = null
	let geometry: THREE.PlaneGeometry | null = null
	let material: THREE.ShaderMaterial | null = null
	let rafId: number | null = null
	let resizeObserver: ResizeObserver | null = null
	let canvasEl: HTMLCanvasElement | null = null
	let pointerMoveHandler: ((event: PointerEvent) => void) | null = null
	let pointerLeaveHandler: ((event: PointerEvent) => void) | null = null
	let windowResizeCleanup: (() => void) | null = null

	const pointerTarget = new THREE.Vector2(0, 0)
	const pointerCurrent = new THREE.Vector2(0, 0)
	const rotationRef = { value: untrack(() => rotation) }
	const autoRotateRef = { value: untrack(() => autoRotate) }
	const rotationVector = new THREE.Vector2(1, 0)
	const rotationOrigin = new THREE.Vector2(0, 0)
	const subscribers: Array<() => void> = []
	const clock = new THREE.Clock()

	setBackgroundContext({
		getCanvas: () => canvasEl,
		getCanvasDimensions: () => ({
			width: canvasEl?.width || 0,
			height: canvasEl?.height || 0,
		}),
		subscribe: (callback) => {
			subscribers.push(callback)
			return () => {
				const idx = subscribers.indexOf(callback)
				if (idx !== -1) subscribers.splice(idx, 1)
			}
		},
	})

	const vertexShaderSource = `
varying vec2 vUv;
void main() {
    vUv = uv;
    gl_Position = vec4(position, 1.0);
}`

	const fragmentShaderSource = `
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
varying vec2 vUv;

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
    gl_FragColor = vec4(rgb, a);
}`

	function hexToVec3(hex: string): THREE.Vector3 {
		const h = hex.replace('#', '').trim()
		const values =
			h.length === 3
				? [parseInt(h[0] + h[0], 16), parseInt(h[1] + h[1], 16), parseInt(h[2] + h[2], 16)]
				: [
						parseInt(h.slice(0, 2), 16),
						parseInt(h.slice(2, 4), 16),
						parseInt(h.slice(4, 6), 16),
					]
		return new THREE.Vector3(values[0] / 255, values[1] / 255, values[2] / 255)
	}

	function applyScalarUniforms() {
		if (!material) return
		rotationRef.value = rotation
		autoRotateRef.value = autoRotate
		material.uniforms.uSpeed.value = speed
		material.uniforms.uScale.value = scale
		material.uniforms.uFrequency.value = frequency
		material.uniforms.uWarpStrength.value = warpStrength
		material.uniforms.uMouseInfluence.value = mouseInfluence
		material.uniforms.uParallax.value = parallax
		material.uniforms.uNoise.value = noise
		material.uniforms.uTransparent.value = transparent ? 1 : 0
		if (renderer) renderer.setClearColor(0x000000, transparent ? 0 : 1)
	}

	function applyColorUniforms() {
		if (!material) return
		const targetColors = (colors || []).filter(Boolean).slice(0, MAX_COLORS).map(hexToVec3)
		const uniformColors = material.uniforms.uColors.value as THREE.Vector3[]
		for (let i = 0; i < MAX_COLORS; i++) {
			if (i < targetColors.length) {
				uniformColors[i].copy(targetColors[i])
			} else {
				uniformColors[i].set(0, 0, 0)
			}
		}
		material.uniforms.uColorCount.value = targetColors.length
	}

	onMount(() => {
		const container = containerRef
		if (!container) return

		scene = new THREE.Scene()
		camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)

		const uColorsArray = Array.from({ length: MAX_COLORS }, () => new THREE.Vector3(0, 0, 0))
		material = new THREE.ShaderMaterial({
			vertexShader: vertexShaderSource,
			fragmentShader: fragmentShaderSource,
			uniforms: {
				uCanvas: { value: new THREE.Vector2(1, 1) },
				uTime: { value: 0 },
				uSpeed: { value: speed },
				uRot: { value: new THREE.Vector2(1, 0) },
				uColorCount: { value: 0 },
				uColors: { value: uColorsArray },
				uTransparent: { value: transparent ? 1 : 0 },
				uScale: { value: scale },
				uFrequency: { value: frequency },
				uWarpStrength: { value: warpStrength },
				uPointer: { value: new THREE.Vector2(0, 0) },
				uMouseInfluence: { value: mouseInfluence },
				uParallax: { value: parallax },
				uNoise: { value: noise },
			},
			premultipliedAlpha: true,
			transparent: true,
		})

		geometry = new THREE.PlaneGeometry(2, 2)
		const mesh = new THREE.Mesh(geometry, material)
		scene.add(mesh)

		renderer = new THREE.WebGLRenderer({
			antialias: false,
			powerPreference: 'high-performance',
			alpha: true,
		})
		renderer.outputColorSpace = THREE.SRGBColorSpace
		renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO))
		renderer.setClearColor(0x000000, transparent ? 0 : 1)
		Object.assign(renderer.domElement.style, {
			width: '100%',
			height: '100%',
			display: 'block',
			position: 'absolute',
			top: '0',
			left: '0',
		})

		canvasEl = renderer.domElement
		container.appendChild(renderer.domElement)

		applyScalarUniforms()
		applyColorUniforms()

		const resize = () => {
			if (!renderer || !material) return
			const width = container.clientWidth || 1
			const height = container.clientHeight || 1
			renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO))
			renderer.setSize(width, height, false)
			;(material.uniforms.uCanvas.value as THREE.Vector2).set(width, height)
			for (const cb of subscribers) cb()
		}

		resize()

		if (typeof ResizeObserver !== 'undefined') {
			resizeObserver = new ResizeObserver(() => resize())
			resizeObserver.observe(container)
		} else {
			const listener = () => resize()
			window.addEventListener('resize', listener)
			windowResizeCleanup = () => window.removeEventListener('resize', listener)
		}

		pointerMoveHandler = (event: PointerEvent) => {
			const rect = container.getBoundingClientRect()
			const x = ((event.clientX - rect.left) / (rect.width || 1)) * 2 - 1
			const y = -(((event.clientY - rect.top) / (rect.height || 1)) * 2 - 1)
			pointerTarget.set(x, y)
		}
		container.addEventListener('pointermove', pointerMoveHandler)

		pointerLeaveHandler = () => {
			pointerTarget.set(0, 0)
		}
		container.addEventListener('pointerleave', pointerLeaveHandler)

		clock.stop()
		clock.start()
		clock.getDelta()

		const loop = () => {
			if (!renderer || !scene || !camera || !material) return
			const dt = clock.getDelta()
			const elapsed = clock.elapsedTime
			material.uniforms.uTime.value = elapsed
			const deg: number = (rotationRef.value % 360) + autoRotateRef.value * elapsed
			const rad = THREE.MathUtils.degToRad(deg)
			rotationVector.set(1, 0).rotateAround(rotationOrigin, rad)
			;(material.uniforms.uRot.value as THREE.Vector2).copy(rotationVector)
			const amt = THREE.MathUtils.clamp(dt * POINTER_SMOOTH, 0, 1)
			pointerCurrent.lerp(pointerTarget, amt)
			;(material.uniforms.uPointer.value as THREE.Vector2).copy(pointerCurrent)
			renderer.render(scene, camera)
			rafId = requestAnimationFrame(loop)
		}

		rafId = requestAnimationFrame(loop)
	})

	onDestroy(() => {
		if (rafId !== null) cancelAnimationFrame(rafId)
		if (resizeObserver) resizeObserver.disconnect()
		if (windowResizeCleanup) windowResizeCleanup()
		const container = containerRef
		if (pointerMoveHandler && container) {
			container.removeEventListener('pointermove', pointerMoveHandler)
		}
		if (pointerLeaveHandler && container) {
			container.removeEventListener('pointerleave', pointerLeaveHandler)
		}
		if (geometry) geometry.dispose()
		if (material) material.dispose()
		if (renderer) {
			renderer.dispose()
			if (container && renderer.domElement.parentElement === container) {
				container.removeChild(renderer.domElement)
			}
		}
		scene = null
		camera = null
		geometry = null
		material = null
		renderer = null
		canvasEl = null
		pointerMoveHandler = null
		pointerLeaveHandler = null
		windowResizeCleanup = null
		resizeObserver = null
		clock.stop()
	})

	$effect(() => {
		applyScalarUniforms()
	})

	$effect(() => {
		applyColorUniforms()
	})
</script>

<div class="absolute inset-0 overflow-hidden" bind:this={containerRef}>
	<div class="relative z-10 h-full w-full">
		{@render children?.()}
	</div>
</div>
