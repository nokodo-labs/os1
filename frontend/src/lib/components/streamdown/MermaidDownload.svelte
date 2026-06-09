<script lang="ts">
	import MenuItem from '$lib/components/primitives/MenuItem.svelte'
	import PopupMenu from '$lib/components/primitives/PopupMenu.svelte'
	import { useStreamdown } from 'svelte-streamdown'
	import { downloadIcon } from './icons.ts'
	import { save } from './utils/save.js'

	let {
		id,
	}: {
		id: string
	} = $props()

	const streamdown = useStreamdown()

	let open = $state(false)
	let anchorEl = $state<HTMLButtonElement | null>(null)

	const attachSvg = (svg: string) => {
		return (node: HTMLElement) => {
			node.innerHTML = svg
		}
	}

	const getSvgElement = (): SVGSVGElement | null => {
		const container = document.querySelector(`[data-streamdown-mermaid="${id}"]`)
		if (!container) return null

		const svgContainer = container.querySelector('[data-mermaid-svg]')
		if (!svgContainer) return null
		if (svgContainer instanceof SVGSVGElement) return svgContainer

		// the rendered SVG lives inside the data-mermaid-svg container
		const svg = svgContainer.querySelector('svg')
		return svg
	}

	const downloadSvg = () => {
		const svg = getSvgElement()
		if (!svg) return

		// clone to avoid mutating the live SVG
		const clonedSvg = svg.cloneNode(true) as SVGSVGElement

		// ensure standalone xmlns
		clonedSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
		clonedSvg.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink')

		// inline computed size so the standalone file has dimensions
		const styles = getComputedStyle(svg)
		if (!clonedSvg.getAttribute('width')) {
			clonedSvg.setAttribute('width', styles.width)
		}
		if (!clonedSvg.getAttribute('height')) {
			clonedSvg.setAttribute('height', styles.height)
		}

		const svgString = new XMLSerializer().serializeToString(clonedSvg)
		save('mermaid-diagram.svg', svgString, 'image/svg+xml')
		open = false
	}

	const downloadPng = () => {
		const svg = getSvgElement()
		if (!svg) return

		// clone to avoid mutating the live SVG
		const clonedSvg = svg.cloneNode(true) as SVGSVGElement

		// ensure standalone xmlns
		clonedSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
		clonedSvg.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink')

		const bbox = svg.getBBox()
		const styles = getComputedStyle(svg)
		const width = parseFloat(styles.width) || bbox.width || 800
		const height = parseFloat(styles.height) || bbox.height || 600

		clonedSvg.setAttribute('width', String(width))
		clonedSvg.setAttribute('height', String(height))

		const svgString = new XMLSerializer().serializeToString(clonedSvg)

		// data URL instead of blob URL to avoid tainted-canvas issues
		const svgDataUrl =
			'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgString)))

		const img = new Image()
		img.onload = () => {
			// render at 2x for a sharper export
			const pixelScale = 2
			const canvas = document.createElement('canvas')
			canvas.width = width * pixelScale
			canvas.height = height * pixelScale
			const ctx = canvas.getContext('2d')
			if (!ctx) return
			ctx.fillStyle = getComputedStyle(document.body).backgroundColor || '#ffffff'
			ctx.fillRect(0, 0, canvas.width, canvas.height)
			ctx.scale(pixelScale, pixelScale)
			ctx.drawImage(img, 0, 0)
			canvas.toBlob((blob) => {
				if (!blob) return
				const url = URL.createObjectURL(blob)
				const link = document.createElement('a')
				link.href = url
				link.download = 'mermaid-diagram.png'
				document.body.appendChild(link)
				link.click()
				document.body.removeChild(link)
				URL.revokeObjectURL(url)
			}, 'image/png')
		}
		img.src = svgDataUrl
		open = false
	}
</script>

<button
	bind:this={anchorEl}
	onclick={() => (open = !open)}
	class={streamdown.theme.components.button}
	title="download"
	aria-label="download diagram"
	type="button"
	data-panzoom-ignore
>
	<span class="h-4 w-4">
		<span aria-hidden="true" {@attach attachSvg(downloadIcon)}></span>
	</span>
</button>

<PopupMenu {open} {anchorEl} onClose={() => (open = false)} estimatedHeight={120}>
	<MenuItem onclick={downloadSvg}>SVG</MenuItem>
	<MenuItem onclick={downloadPng}>PNG</MenuItem>
</PopupMenu>
