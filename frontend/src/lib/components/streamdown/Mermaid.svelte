<script module lang="ts">
	export type WheelZoomActivation = 'modifier' | 'hover' | 'both'

	// shared wheel-zoom activation: 'modifier' (ctrl + scroll), 'hover' (scroll
	// after a brief hover), or 'both'. mermaid is rendered inside streamdown so it
	// has no prop channel from the page - this module rune bridges that gap and
	// lets the debug page flip the mode live for every chart.
	export const wheelZoom = $state<{ mode: WheelZoomActivation }>({ mode: 'modifier' })
</script>

<script lang="ts">
	import type { Tokens } from 'marked'
	import type { MermaidConfig } from 'mermaid'
	import { onDestroy, onMount } from 'svelte'
	import { useStreamdown } from 'svelte-streamdown'
	import {
		checkIcon,
		copyIcon,
		fitViewIcon,
		fullscreenIcon,
		zoomInIcon,
		zoomOutIcon,
	} from './icons.ts'
	import MermaidDownload from './MermaidDownload.svelte'
	import { usePanzoom } from './utils/panzoom.svelte.js'

	const streamdown = useStreamdown()

	const {
		token,
		id,
	}: {
		token: Tokens.Code
		id: string
	} = $props()

	type MermaidApi = {
		initialize: (config: MermaidConfig) => void
		render: (id: string, code: string) => Promise<{ svg: string }>
	}

	const attachSvg = (svg: string) => {
		return (node: HTMLElement) => {
			node.innerHTML = svg
		}
	}

	let mermaid = $state<MermaidApi | null>(null)
	let mermaidConfigKey = ''
	let lastRenderedCode = ''
	let renderSeq = 0
	let renderTimer: ReturnType<typeof setTimeout> | null = null
	let hasRendered = $state(false)
	let hasRenderError = $state(false)
	let copied = $state(false)
	let copyTimer: ReturnType<typeof setTimeout> | null = null
	// only fall back to raw source if a diagram never rendered; once one renders,
	// later partial snapshots that fail keep the last good render.
	const showFallback = $derived(hasRenderError && !hasRendered)
	onMount(async () => {
		mermaid = (await import('mermaid')).default
	})
	onDestroy(() => {
		if (renderTimer) clearTimeout(renderTimer)
		if (copyTimer) clearTimeout(copyTimer)
	})

	// copy the raw mermaid source as a fenced markdown block, like code blocks.
	const copyRaw = async () => {
		await navigator.clipboard.writeText(`\`\`\`mermaid\n${token.text.trim()}\n\`\`\`\n`)
		copied = true
		if (copyTimer) clearTimeout(copyTimer)
		copyTimer = setTimeout(() => (copied = false), 2000)
	}

	// wheel-zoom activation comes from the shared wheelZoom module rune above.
	const panzoom = usePanzoom({
		minZoom: 0.02,
		maxZoom: 32,
		zoomSpeed: 1,
		modifierKey: 'Control',
		activateMouseWheel: true,
		wheelActivation: wheelZoom.mode,
	})

	const sanitizeMermaidCode = (code: string): string => {
		try {
			let sanitized = code

			const stripControlChars = (input: string): string => {
				let out = ''
				for (let i = 0; i < input.length; i++) {
					const charCode = input.charCodeAt(i)
					const isAllowedWhitespace = charCode === 9 || charCode === 10 || charCode === 13
					const isControlChar = (charCode >= 0 && charCode <= 31) || charCode === 127
					if (isControlChar && !isAllowedWhitespace) continue
					out += input[i]
				}
				return out
			}

			// 1. remove byte order mark (BOM)
			sanitized = sanitized.replace(/^\uFEFF/, '')

			// 2. normalize unicode (NFC form for consistent rendering)
			sanitized = sanitized.normalize('NFC')

			// 3. remove invisible/zero-width characters
			sanitized = sanitized.replace(/[\u200B-\u200F\u2028-\u202F\u205F-\u206F]/g, '')

			// 4. remove control characters (except tab, line feed, carriage return)
			sanitized = stripControlChars(sanitized)

			// 5. normalize line endings to LF
			sanitized = sanitized.replace(/\r\n/g, '\n').replace(/\r/g, '\n')

			// 6. decode common HTML entities that might appear in mermaid code
			const htmlEntities: Record<string, string> = {
				'&lt;': '<',
				'&gt;': '>',
				'&amp;': '&',
				'&quot;': '"',
				'&#39;': "'",
				'&apos;': "'",
				'&nbsp;': ' ',
				'&hellip;': '...',
				'&mdash;': '--',
				'&ndash;': '-',
				'&lsquo;': "'",
				'&rsquo;': "'",
				'&ldquo;': '"',
				'&rdquo;': '"',
			}

			for (const [entity, replacement] of Object.entries(htmlEntities)) {
				sanitized = sanitized.replace(new RegExp(entity, 'g'), replacement)
			}

			// 7. convert smart quotes and other quote variants to standard quotes
			sanitized = sanitized
				.replace(/[\u2018\u2019]/g, "'") // smart single quotes
				.replace(/[\u201C\u201D]/g, '"') // smart double quotes
				.replace(/[\u2013\u2014]/g, '-') // em/en dashes
				.replace(/\u2026/g, '...') // horizontal ellipsis

			// 8. remove non-breaking spaces and other special spaces
			sanitized = sanitized.replace(
				/[\u00A0\u1680\u180E\u2000-\u200A\u202F\u205F\u3000]/g,
				' '
			)

			// 9. remove trailing semicolons that might break parsing
			sanitized = sanitized.replace(/;+\s*$/gm, '')

			// 10. trim outer whitespace and ensure a single trailing newline
			sanitized = sanitized.trim()
			if (sanitized && !sanitized.endsWith('\n')) {
				sanitized += '\n'
			}

			return sanitized
		} catch (error) {
			console.warn('Error during Mermaid code sanitization:', error)
			return code
		}
	}

	const applyRenderedSvg = (svgTarget: SVGSVGElement, uniqueId: string, svgString: string) => {
		const parsed = new DOMParser().parseFromString(svgString, 'image/svg+xml')
		const renderedSvg = parsed.documentElement
		if (renderedSvg.nodeName.toLowerCase() === 'parsererror') {
			svgTarget.innerHTML = svgString
			return
		}

		for (const attribute of Array.from(svgTarget.attributes)) {
			if (attribute.name !== 'data-mermaid-svg') svgTarget.removeAttribute(attribute.name)
		}

		svgTarget.id = uniqueId
		for (const attribute of Array.from(renderedSvg.attributes)) {
			if (attribute.name !== 'id') svgTarget.setAttribute(attribute.name, attribute.value)
		}

		const viewBox = renderedSvg.getAttribute('viewBox')
		const viewBoxParts = viewBox?.split(/[\s,]+/).map((part) => Number(part)) ?? []
		const viewBoxWidth = viewBoxParts.length === 4 ? viewBoxParts[2] : Number.NaN
		const viewBoxHeight = viewBoxParts.length === 4 ? viewBoxParts[3] : Number.NaN
		const attrWidth = Number.parseFloat(renderedSvg.getAttribute('width') ?? '')
		const attrHeight = Number.parseFloat(renderedSvg.getAttribute('height') ?? '')
		const width = Number.isFinite(viewBoxWidth) && viewBoxWidth > 0 ? viewBoxWidth : attrWidth
		const height =
			Number.isFinite(viewBoxHeight) && viewBoxHeight > 0 ? viewBoxHeight : attrHeight
		if (Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0) {
			svgTarget.parentElement?.style.setProperty(
				'--mermaid-aspect-ratio',
				`${width} / ${height}`
			)
			svgTarget.setAttribute('width', String(width))
			svgTarget.setAttribute('height', String(height))
			svgTarget.style.width = `${width}px`
			svgTarget.style.height = `${height}px`
			svgTarget.style.maxWidth = 'none'
			svgTarget.style.maxHeight = 'none'
		}

		svgTarget.setAttribute('preserveAspectRatio', 'xMidYMid meet')
		svgTarget.innerHTML = renderedSvg.innerHTML
	}

	const renderMermaid = async (code: string, element: HTMLElement) => {
		try {
			if (!mermaid) return
			const sanitizedCode = sanitizeMermaidCode(code)
			const svgTarget = element.querySelector('[data-mermaid-svg]') as SVGSVGElement | null
			if (sanitizedCode === lastRenderedCode && svgTarget?.innerHTML) return

			const defaultConfig: MermaidConfig = {
				theme: 'base',
				startOnLoad: false,
				securityLevel: 'strict',
				fontFamily: 'monospace',
				suppressErrorRendering: true,

				flowchart: {
					useMaxWidth: false,
					htmlLabels: true,
					curve: 'basis',
				},
				...(streamdown.mermaidConfig || {}),
			}

			const nextConfigKey = JSON.stringify(defaultConfig)
			if (nextConfigKey !== mermaidConfigKey) {
				mermaid.initialize(defaultConfig)
				mermaidConfigKey = nextConfigKey
			}

			const chartHash = code.split('').reduce((acc, char) => {
				return ((acc << 5) - acc + char.charCodeAt(0)) | 0
			}, 0)

			const uniqueId = `mermaid-${Math.abs(chartHash)}-${Date.now()}-${Math.random()
				.toString(36)
				.substring(2, 9)}`
			const seq = ++renderSeq

			const { svg: svgString } = await mermaid.render(uniqueId, sanitizedCode)
			if (seq !== renderSeq) return

			if (svgTarget) {
				applyRenderedSvg(svgTarget, uniqueId, svgString)

				panzoom.zoomToFit()
				lastRenderedCode = sanitizedCode
				hasRendered = true
				hasRenderError = false
			}
		} catch (err) {
			console.warn('Mermaid rendering error:', err)
			hasRenderError = true
		}
	}

	// debounce: streamed source changes rapidly and is often incomplete, so
	// rendering every snapshot spams parse errors and janks. render once it settles.
	const scheduleRender = (code: string, element: HTMLElement) => {
		if (renderTimer) clearTimeout(renderTimer)
		renderTimer = setTimeout(() => {
			renderTimer = null
			void renderMermaid(code, element)
		}, 180)
	}
</script>

<div data-streamdown-mermaid={id}>
	{#if mermaid}
		<div
			style={streamdown.isMounted ? streamdown.animationBlockStyle : ''}
			class={streamdown.theme.mermaid.base}
			{@attach (node) => scheduleRender(token.text, node)}
			data-expanded="false"
			data-fallback={showFallback}
		>
			<svg {@attach panzoom.attach} data-mermaid-svg></svg>
			{#if showFallback}
				<pre class="mermaid-fallback"><code>{token.text}</code></pre>
			{/if}
			{#if streamdown.controls.mermaid && !showFallback}
				<div class={`${streamdown.theme.mermaid.buttons} mermaid-controls`}>
					<button
						class={streamdown.theme.components.button}
						aria-label="zoom to fit"
						onclick={() => panzoom.zoomToFit()}
						data-panzoom-ignore
					>
						{#if streamdown.icons?.fitView}
							{@render streamdown.icons.fitView()}
						{:else}
							<span
								class="h-4 w-4"
								aria-hidden="true"
								{@attach attachSvg(fitViewIcon)}
							></span>
						{/if}
					</button>
					<button
						class={streamdown.theme.components.button}
						aria-label="zoom in"
						onclick={() => panzoom.zoomIn()}
						data-panzoom-ignore
					>
						{#if streamdown.icons?.zoomIn}
							{@render streamdown.icons.zoomIn()}
						{:else}
							<span class="h-4 w-4" aria-hidden="true" {@attach attachSvg(zoomInIcon)}
							></span>
						{/if}
					</button>
					<button
						class={streamdown.theme.components.button}
						aria-label="zoom out"
						onclick={() => panzoom.zoomOut()}
						data-panzoom-ignore
					>
						{#if streamdown.icons?.zoomOut}
							{@render streamdown.icons.zoomOut()}
						{:else}
							<span
								class="h-4 w-4"
								aria-hidden="true"
								{@attach attachSvg(zoomOutIcon)}
							></span>
						{/if}
					</button>
					<button
						class={streamdown.theme.components.button}
						aria-label="toggle expand"
						onclick={() => panzoom.toggleExpand()}
						data-panzoom-ignore
					>
						{#if streamdown.icons?.fullscreen}
							{@render streamdown.icons.fullscreen()}
						{:else}
							<span
								class="h-4 w-4"
								aria-hidden="true"
								{@attach attachSvg(fullscreenIcon)}
							></span>
						{/if}
					</button>
					<button
						class={streamdown.theme.components.button}
						aria-label={copied ? 'copied' : 'copy diagram source'}
						onclick={() => void copyRaw()}
						data-panzoom-ignore
					>
						<span
							class="h-4 w-4"
							aria-hidden="true"
							{@attach attachSvg(copied ? checkIcon : copyIcon)}
						></span>
					</button>
					<MermaidDownload {id} />
				</div>
			{/if}
		</div>
	{:else}
		<div class={streamdown.theme.mermaid.base}></div>
	{/if}
</div>

<style>
	:global([data-expanded='true']) {
		position: fixed;
		top: max(16px, env(safe-area-inset-top));
		right: 16px;
		bottom: max(16px, env(safe-area-inset-bottom));
		left: 16px;
		width: auto;
		height: auto;
		z-index: 2147483647;
		margin: 0px;
		overflow: hidden;
		border-radius: clamp(18px, 2.4vw, 32px);
		box-shadow: 0 24px 72px rgba(0, 0, 0, 0.38);
	}

	:global([data-expanded='true'] svg[data-mermaid-svg]) {
		border-radius: inherit;
	}

	:global([data-streamdown-mermaid] [data-expanded]) {
		position: relative;
		overflow: hidden;
	}

	:global([data-streamdown-mermaid] [data-expanded='false']) {
		/* pin the width so the aspect-ratio derives height from it. without this,
		   the upstream min-height (500px) on a wide diagram makes the box grow its
		   own width to satisfy the ratio, overflowing the parent and forcing
		   horizontal page scroll. */
		width: 100%;
		aspect-ratio: var(--mermaid-aspect-ratio, 16 / 9);
	}

	/* failed diagrams: drop the fixed aspect-ratio box and show raw source */
	:global([data-streamdown-mermaid] [data-fallback='true']) {
		aspect-ratio: auto;
		overflow: auto;
	}

	:global([data-streamdown-mermaid] [data-fallback='true'] svg[data-mermaid-svg]) {
		display: none;
	}

	.mermaid-fallback {
		position: relative;
		z-index: 1;
		margin: 0;
		padding: 0.75rem 1rem;
		overflow-x: auto;
		font-family: var(--font-mono, monospace);
		font-size: 0.8125rem;
		line-height: 1.5;
		white-space: pre;
		color: var(--muted-foreground, inherit);
	}

	:global([data-streamdown-mermaid] svg[data-mermaid-svg]) {
		position: absolute;
		top: 0;
		left: 0;
		z-index: 0;
		display: block;
		width: auto;
		height: auto;
	}

	:global([data-streamdown-mermaid] .mermaid-controls) {
		position: absolute;
		top: 0.75rem;
		right: 0.75rem;
		z-index: 20;
		pointer-events: auto;
	}

	/* mobile: let swipes scroll the page over charts, and keep wide diagrams
	   clipped to their box so they never force horizontal page scroll */
	@media (pointer: coarse) {
		:global([data-streamdown-mermaid] [data-expanded='false']) {
			touch-action: pan-y !important;
		}

		:global([data-streamdown-mermaid] [data-expanded='false'] svg[data-mermaid-svg]) {
			pointer-events: none !important;
		}
	}

	/* hide mermaid's temporary rendering containers */
	:global(div[id^='dmermaid-']) {
		position: absolute !important;
		left: -9999px !important;
		top: -9999px !important;
		visibility: hidden !important;
		pointer-events: none !important;
	}
</style>
