<script lang="ts">
	import type { Tokens } from 'marked'
	import type { MermaidConfig } from 'mermaid'
	import { onMount } from 'svelte'
	import { useStreamdown } from 'svelte-streamdown'
	import { fitViewIcon, fullscreenIcon, zoomInIcon, zoomOutIcon } from './icons.ts'
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

	let mermaid = $state<any>(null)
	onMount(async () => {
		mermaid = (await import('mermaid')).default
	})

	const panzoom = usePanzoom({
		minZoom: 0.5,
		maxZoom: 4,
		zoomSpeed: 1,
		modifierKey: 'Control', // Check for Ctrl key
		activateMouseWheel: true, // Enable wheel logic (which checks modifierKey)
	})

	const sanitizeMermaidCode = (code: string): string => {
		try {
			let sanitized = code

			// 1. Remove Byte Order Mark (BOM)
			sanitized = sanitized.replace(/^\uFEFF/, '')

			// 2. Normalize Unicode (NFC form for consistent rendering)
			sanitized = sanitized.normalize('NFC')

			// 3. Remove invisible/zero-width characters
			sanitized = sanitized.replace(/[\u200B-\u200F\u2028-\u202F\u205F-\u206F]/g, '')

			// 4. Remove control characters (except tab, line feed, carriage return)
			sanitized = sanitized.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '')

			// 5. Normalize line endings to LF
			sanitized = sanitized.replace(/\r\n/g, '\n').replace(/\r/g, '\n')

			// 6. Decode common HTML entities that might appear in Mermaid code
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

			// 7. Convert smart quotes and other quote variants to standard quotes
			sanitized = sanitized
				.replace(/[\u2018\u2019]/g, "'") // Smart single quotes
				.replace(/[\u201C\u201D]/g, '"') // Smart double quotes
				.replace(/[\u2013\u2014]/g, '-') // Em/en dashes
				.replace(/\u2026/g, '...') // Horizontal ellipsis

			// 8. Trim leading/trailing whitespace from each line and remove empty lines
			sanitized = sanitized
				.split('\n')
				.map((line) => line.trim())
				.filter((line) => line.length > 0)
				.join('\n')

			// 9. Normalize multiple spaces/tabs to single space (but preserve indentation in code blocks)
			sanitized = sanitized.replace(/[ \t]+/g, ' ')

			// 10. Handle over-escaped characters (common in copied code)
			// Convert double backslashes to single (except in JSON strings)
			sanitized = sanitized.replace(/\\\\(?![\\"])/g, '\\')

			// 11. Remove non-breaking spaces and other special spaces
			sanitized = sanitized.replace(
				/[\u00A0\u1680\u180E\u2000-\u200A\u202F\u205F\u3000]/g,
				' '
			)

			// 12. Ensure proper spacing around operators and keywords
			// Add space after commas if missing (common in CSV-like data)
			sanitized = sanitized.replace(/,([^\s])/g, ', $1')

			// 13. Clean up Mermaid-specific issues
			// Remove trailing semicolons that might break parsing
			sanitized = sanitized.replace(/;+\s*$/gm, '')

			// Ensure proper spacing in flowchart syntax
			sanitized = sanitized.replace(
				/([A-Za-z0-9_]+)(\-\-|\-\-\>|\-\.\-|\-\.\-\>|\=\=|\=\=\>|\=\.\=\>|\=\.\-\>)/g,
				'$1 $2'
			)

			// 14. Final cleanup: trim and ensure single trailing newline
			sanitized = sanitized.trim()
			if (sanitized && !sanitized.endsWith('\n')) {
				sanitized += '\n'
			}

			return sanitized
		} catch (error) {
			console.warn('Error during Mermaid code sanitization:', error)
			// Return original code if sanitization fails
			return code
		}
	}

	const renderMermaid = async (code: string, element: HTMLElement) => {
		try {
			// Sanitize the code first
			const sanitizedCode = sanitizeMermaidCode(code)

			// Default configuration
			const defaultConfig: MermaidConfig = {
				theme: 'base',
				startOnLoad: false,
				securityLevel: 'strict',
				fontFamily: 'monospace',
				suppressErrorRendering: true,

				flowchart: {
					useMaxWidth: true,
					htmlLabels: true,
					curve: 'basis',
				},
				...(streamdown.mermaidConfig || {}),
			}

			// Initialize mermaid with merged config
			mermaid.initialize(defaultConfig)

			const chartHash = code.split('').reduce((acc, char) => {
				return ((acc << 5) - acc + char.charCodeAt(0)) | 0
			}, 0)

			const uniqueId = `mermaid-${Math.abs(chartHash)}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`

			// Render the diagram
			const { svg: svgString } = await mermaid.render(uniqueId, sanitizedCode)

			// Insert the SVG into the target element
			const svgTarget = element.querySelector('[data-mermaid-svg]') as SVGElement
			if (svgTarget) {
				svgTarget.innerHTML = svgString
				svgTarget.id = uniqueId

				// Apply any additional attributes from the rendered SVG
				const tempSvg = new DOMParser().parseFromString(
					svgString,
					'image/svg+xml'
				).documentElement
				Array.from(tempSvg.attributes).forEach((attribute) => {
					if (attribute.name !== 'id') {
						svgTarget.setAttribute(attribute.name, attribute.value)
					}
				})

				panzoom.zoomToFit()
				panzoom.zoomToFit()
			}
		} catch (err) {
			console.warn('Mermaid rendering error:', err)
			// Could show error state in UI here
		}
	}
</script>

{#snippet customFitViewIcon()}
	{@html fitViewIcon}
{/snippet}

{#snippet customZoomInIcon()}
	{@html zoomInIcon}
{/snippet}

{#snippet customZoomOutIcon()}
	{@html zoomOutIcon}
{/snippet}

{#snippet customFullscreenIcon()}
	{@html fullscreenIcon}
{/snippet}

<div data-streamdown-mermaid={id}>
	{#if mermaid}
		<div
			style={streamdown.isMounted ? streamdown.animationBlockStyle : ''}
			class={streamdown.theme.mermaid.base}
			{@attach (node) => renderMermaid(token.text, node)}
			data-expanded={'false'}
		>
			{#if streamdown.controls.mermaid}
				<div class={streamdown.theme.mermaid.buttons}>
					<button
						class={streamdown.theme.components.button}
						aria-label="zoom to fit"
						onclick={() => panzoom.zoomToFit()}
						data-panzoom-ignore
					>
						{@render (streamdown.icons?.fitView || customFitViewIcon)()}
					</button>
					<button
						class={streamdown.theme.components.button}
						aria-label="zoom in"
						onclick={() => panzoom.zoomIn()}
						data-panzoom-ignore
					>
						{@render (streamdown.icons?.zoomIn || customZoomInIcon)()}
					</button>
					<button
						class={streamdown.theme.components.button}
						aria-label="zoom out"
						onclick={() => panzoom.zoomOut()}
						data-panzoom-ignore
					>
						{@render (streamdown.icons?.zoomOut || customZoomOutIcon)()}
					</button>
					<button
						class={streamdown.theme.components.button}
						aria-label="toggle expand"
						onclick={() => panzoom.toggleExpand()}
						data-panzoom-ignore
					>
						{@render (streamdown.icons?.fullscreen || customFullscreenIcon)()}
					</button>
					<MermaidDownload {id} />
				</div>
			{/if}
			<svg {@attach panzoom.attach} data-mermaid-svg></svg>
		</div>
	{:else}
		<div class={streamdown.theme.mermaid.base}></div>
	{/if}
</div>

<style>
	:global([data-expanded='true']) {
		position: fixed;
		top: 16px;
		left: 16px;
		width: calc(100vw - 32px);
		height: calc(100vh - 32px);
		z-index: 2147483647;
		margin: 0px;
	}

	/* Hide Mermaid's temporary rendering containers */
	:global(div[id^='dmermaid-']) {
		position: absolute !important;
		left: -9999px !important;
		top: -9999px !important;
		visibility: hidden !important;
		pointer-events: none !important;
	}
</style>
