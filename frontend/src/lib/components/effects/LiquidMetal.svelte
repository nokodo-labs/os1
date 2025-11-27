<script lang="ts">
    import { onMount } from 'svelte'
    import * as THREE from 'three'

    interface Props {
        speed?: number
        color1?: string
        color2?: string
    }

    let { speed = 0.2, color1 = '#ffffff', color2 = '#000000' }: Props = $props()

    let container: HTMLDivElement
    let renderer: THREE.WebGLRenderer
    let scene: THREE.Scene
    let camera: THREE.OrthographicCamera
    let material: THREE.ShaderMaterial
    let animationId: number
    let startTime = 0

    const vertexShader = `
        varying vec2 vUv;
        void main() {
            vUv = uv;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
    `

    const fragmentShader = `
        uniform float uTime;
        uniform vec2 uResolution;
        uniform float uSpeed;
        
        varying vec2 vUv;

        // Simplex 2D noise
        vec3 permute(vec3 x) { return mod(((x*34.0)+1.0)*x, 289.0); }

        float snoise(vec2 v){
            const vec4 C = vec4(0.211324865405187, 0.366025403784439,
                    -0.577350269189626, 0.024390243902439);
            vec2 i  = floor(v + dot(v, C.yy) );
            vec2 x0 = v - i + dot(i, C.xx);
            vec2 i1;
            i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
            vec4 x12 = x0.xyxy + C.xxzz;
            x12.xy -= i1;
            i = mod(i, 289.0);
            vec3 p = permute( permute( i.y + vec3(0.0, i1.y, 1.0 ))
            + i.x + vec3(0.0, i1.x, 1.0 ));
            vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.xy,x12.xy), dot(x12.zw,x12.zw)), 0.0);
            m = m*m ;
            m = m*m ;
            vec3 x = 2.0 * fract(p * C.www) - 1.0;
            vec3 h = abs(x) - 0.5;
            vec3 ox = floor(x + 0.5);
            vec3 a0 = x - ox;
            m *= 1.79284291400159 - 0.85373472095314 * ( a0*a0 + h*h );
            vec3 g;
            g.x  = a0.x  * x0.x  + h.x  * x0.y;
            g.yz = a0.yz * x12.xz + h.yz * x12.yw;
            return 130.0 * dot(m, g);
        }

        void main() {
            vec2 uv = vUv;
            // Fix aspect ratio to prevent stretching
            float aspect = uResolution.x / uResolution.y;
            uv.x *= aspect;

            float t = uTime * uSpeed;

            // --- Liquid Metal Logic ---
            
            // 1. Base Flow (Extremely large, barely moving)
            // Scale 0.2 = very large blobs
            float n1 = snoise(uv * 0.2 + vec2(t * 0.05, t * 0.02));
            
            // 2. Detail Flow (Subtle surface variation)
            // Scale 0.5 = large ripples
            float n2 = snoise(uv * 0.5 - vec2(t * 0.02) + n1 * 0.2);
            
            // 3. Surface Normals (Fake)
            float height = n2;
            
            // 4. Environment Mapping (Fake)
            // Chrome/Mercury is characterized by sharp transitions but smooth curves
            
            // Smoothstep controls the "contrast" of the reflection
            float metal = smoothstep(-0.4, 0.4, height);
            
            // Add "ridges" for specular highlights
            // Frequency 1.5 = very few, broad highlights
            float ridges = sin(height * 1.5 + t * 0.1);
            ridges = smoothstep(0.95, 1.0, ridges); // Extremely sharp, thin highlights
            
            // Colors
            vec3 dark = vec3(0.08, 0.08, 0.1); // Deep dark steel
            vec3 mid = vec3(0.7, 0.7, 0.75);    // Bright silver
            vec3 light = vec3(0.98, 0.98, 1.0); // Pure white highlight
            
            // Mix based on height/angle
            vec3 color = mix(dark, mid, metal);
            color = mix(color, light, ridges);
            
            // Add a subtle iridescence/chromatic aberration at edges
            float aberration = snoise(uv * 1.0 + t);
            color += vec3(0.01, 0.0, 0.01) * aberration;

            gl_FragColor = vec4(color, 1.0);
        }
    `

    function init() {
        if (!container) return

        // Scene setup
        scene = new THREE.Scene()
        camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)

        renderer = new THREE.WebGLRenderer({
            alpha: true,
            antialias: true,
            powerPreference: 'high-performance',
        })
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
        container.appendChild(renderer.domElement)

        // Geometry
        const geometry = new THREE.PlaneGeometry(2, 2)

        // Material
        material = new THREE.ShaderMaterial({
            vertexShader,
            fragmentShader,
            uniforms: {
                uTime: { value: 0 },
                uResolution: { value: new THREE.Vector2(1, 1) },
                uSpeed: { value: speed },
            },
        })

        const mesh = new THREE.Mesh(geometry, material)
        scene.add(mesh)

        handleResize()
        animate()
    }

    function handleResize() {
        if (!container || !renderer || !material) return
        const width = container.clientWidth
        const height = container.clientHeight
        renderer.setSize(width, height)
        material.uniforms.uResolution.value.set(width, height)
    }

    function animate() {
        animationId = requestAnimationFrame(animate)
        const time = (performance.now() - startTime) * 0.001
        if (material) {
            material.uniforms.uTime.value = time
        }
        renderer.render(scene, camera)
    }

    onMount(() => {
        startTime = performance.now()
        init()

        const resizeObserver = new ResizeObserver(() => handleResize())
        resizeObserver.observe(container)

        return () => {
            cancelAnimationFrame(animationId)
            resizeObserver.disconnect()
            if (renderer) {
                renderer.dispose()
                container?.removeChild(renderer.domElement)
            }
            if (material) material.dispose()
        }
    })
</script>

<div bind:this={container} class="h-full w-full overflow-hidden rounded-full"></div>
