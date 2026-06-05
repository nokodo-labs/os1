<script lang="ts">
	import { useStreamdown } from 'svelte-streamdown'
	import { scale } from 'svelte/transition'
	import { downloadIcon } from './icons.ts'
	import { Popover } from './popover.svelte.js'
	import { save } from './utils/save.js'
	import { useClickOutside } from './utils/useClickOutside.svelte.js'
	import { useKeyDown } from './utils/useKeyDown.svelte.js'

	let {
		id,
		rawCode,
	}: {
		id: string
		rawCode: string
	} = $props()

	const streamdown = useStreamdown()
	const popover = new Popover()

	const attachSvg = (svg: string) => {
		return (node: HTMLElement) => {
			node.innerHTML = svg
		}
	}

	useKeyDown({
		keys: ['Escape'],
		get isActive() {
			return popover.isOpen
		},
		callback: () => {
			popover.isOpen = false
		},
	})

	const clickOutside = useClickOutside({
		get isActive() {
			return popover.isOpen
		},
		callback: () => {
			popover.isOpen = false
		},
	})

	const getSvgElement = (): SVGSVGElement | null => {
		const container = document.querySelector(`[data-streamdown-mermaid="${id}"]`)
		if (!container) return null

		const svgContainer = container.querySelector('[data-mermaid-svg]')
		if (!svgContainer) return null
		if (svgContainer instanceof SVGSVGElement) return svgContainer

		// The actual SVG is rendered inside the data-mermaid-svg container
		const svg = svgContainer.querySelector('svg')
		return svg
	}

	const copyRawMarkdown = async () => {
		const markdown = `\`\`\`mermaid\n${rawCode.trim()}\n\`\`\`\n`
		await navigator.clipboard.writeText(markdown)
		popover.isOpen = false
	}

	const downloadSvg = () => {
		const svg = getSvgElement()
		if (!svg) return

		// Clone the SVG to avoid modifying the original
		const clonedSvg = svg.cloneNode(true) as SVGSVGElement

		// Ensure the SVG has proper xmlns
		clonedSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
		clonedSvg.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink')

		// Get computed styles and inline them for standalone SVG
		const styles = getComputedStyle(svg)
		if (!clonedSvg.getAttribute('width')) {
			clonedSvg.setAttribute('width', styles.width)
		}
		if (!clonedSvg.getAttribute('height')) {
			clonedSvg.setAttribute('height', styles.height)
		}

		const svgString = new XMLSerializer().serializeToString(clonedSvg)
		save('mermaid-diagram.svg', svgString, 'image/svg+xml')
		popover.isOpen = false
	}

	const downloadPng = async () => {
		const svg = getSvgElement()
		if (!svg) return

		// Clone the SVG to avoid modifying the original
		const clonedSvg = svg.cloneNode(true) as SVGSVGElement

		// Ensure the SVG has proper xmlns
		clonedSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
		clonedSvg.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink')

		// Get dimensions
		const bbox = svg.getBBox()
		const styles = getComputedStyle(svg)
		const width = parseFloat(styles.width) || bbox.width || 800
		const height = parseFloat(styles.height) || bbox.height || 600

		// Set explicit dimensions on the cloned SVG
		clonedSvg.setAttribute('width', String(width))
		clonedSvg.setAttribute('height', String(height))

		// Serialize SVG to string
		const svgString = new XMLSerializer().serializeToString(clonedSvg)

		// Use data URL instead of blob URL to avoid tainted canvas issues
		const svgDataUrl =
			'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgString)))

		// Create image to draw on canvas
		const img = new Image()
		img.onload = () => {
			const canvas = document.createElement('canvas')
			canvas.width = width
			canvas.height = height
			const ctx = canvas.getContext('2d')
			if (!ctx) return
			ctx.fillStyle = getComputedStyle(document.body).backgroundColor || '#ffffff' // Use body background or white
			ctx.fillRect(0, 0, width, height) // Fill background
			ctx.drawImage(img, 0, 0)
			const png = canvas.toDataURL('image/png')
			save('mermaid-diagram.png', atob(png.split(',')[1]), 'image/png')
			popover.isOpen = false
		}
		img.src = svgDataUrl
	}
</script>

<div class="relative">
	<button
		onclick={() => (popover.isOpen = !popover.isOpen)}
		use:popover.reference
		class={streamdown.theme.components.button}
		title="download"
		data-panzoom-ignore
	>
		<span class="h-4 w-4">
			<span aria-hidden="true" {@attach attachSvg(downloadIcon)}></span>
		</span>
	</button>

	{#if popover.isOpen}
		<dialog
			id="mermaid-download-popover"
			aria-modal="false"
			transition:scale|global={{ start: 0.95, duration: 100 }}
			use:clickOutside.attachment
			use:popover.popoverAttachment
			open
			style:width="fit-content !important"
			style:min-width="fit-content !important"
			class={streamdown.theme.components.popover}
		>
			<button
				style="width: 100%; text-align: left; justify-content: flex-start; padding: 0.5rem 1rem; margin: 0.2rem 0;"
				onclick={downloadSvg}
				class={streamdown.theme.components.button}
			>
				SVG
			</button>
			<button
				style="width: 100%; text-align: left; justify-content: flex-start; padding: 0.5rem 1rem; margin: 0.2rem 0;"
				onclick={downloadPng}
				class={streamdown.theme.components.button}
			>
				PNG
			</button>
			<button
				style="width: 100%; text-align: left; justify-content: flex-start; padding: 0.5rem 1rem; margin: 0.2rem 0;"
				onclick={() => void copyRawMarkdown()}
				class={streamdown.theme.components.button}
			>
				copy raw MD
			</button>
		</dialog>
	{/if}
</div>
