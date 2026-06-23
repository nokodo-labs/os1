<script lang="ts">
	import MenuItem from '$lib/components/primitives/MenuItem.svelte'
	import PopupMenu from '$lib/components/primitives/PopupMenu.svelte'
	import { onDestroy } from 'svelte'
	import { useStreamdown } from 'svelte-streamdown'
	import { checkIcon, copyIcon, downloadIcon } from './icons.ts'
	import { save } from './utils/save.js'

	let {
		id,
		raw,
	}: {
		id: string
		raw: string
	} = $props()

	const streamdown = useStreamdown()

	type Format = 'Markdown' | 'HTML' | 'CSV'

	let downloadOpen = $state(false)
	let copyOpen = $state(false)
	let copied = $state(false)
	let copyTimer: ReturnType<typeof setTimeout> | null = null
	let downloadAnchor = $state<HTMLButtonElement | null>(null)
	let copyAnchor = $state<HTMLButtonElement | null>(null)

	const attachSvg = (svg: string) => {
		return (node: HTMLElement) => {
			node.innerHTML = svg
		}
	}

	onDestroy(() => {
		if (copyTimer) clearTimeout(copyTimer)
	})

	const toHtml = (): string => {
		const table = document.querySelector(`[data-streamdown-table="${id}"]`)
		if (!table) return ''
		let html = (table.cloneNode(true) as HTMLElement).outerHTML
		// strip comments, classes, and styles so the export is clean markup
		html = html.replace(/<!--[\s\S]*?-->/g, '')
		html = html.replace(/class="[^"]*"/g, '')
		html = html.replace(/style="[^"]*"/g, '')
		html = html.replace(/<([^>]+)>\s+</g, '<$1><')
		html = html.replace(/\s+>/g, '>')
		html = html.replace(/<\s+/g, '<')
		html = html.replace(/<([^>]+)>/g, (match) => match.replace(/\s+/g, ' '))
		return html
	}

	const toCsv = (): string => {
		const table = document.querySelector(`[data-streamdown-table="${id}"]`)
		if (!table) return ''
		const rows = table.querySelectorAll('tr')
		const rowSpanFills: Array<{ rowIndex: number; colIndex: number; colSpan: number }> = []

		const matrix = Array.from(rows).reduce<string[][]>((acc, row, rowIndex) => {
			const cells = row.querySelectorAll('td, th')
			const rowData: string[] = []
			let actualCol = 0

			Array.from(cells).forEach((cell) => {
				const colSpan = parseInt(cell.getAttribute('colspan') || '1')
				const rowSpan = parseInt(cell.getAttribute('rowspan') || '1')

				// quote cells containing commas, quotes, or newlines
				const content = cell.textContent || ''
				const needsQuoting = /[,"\n]/.test(content)
				const escapedContent = content.replace(/"/g, '""')
				rowData.push(needsQuoting ? `"${escapedContent}"` : content)

				for (let i = 0; i < colSpan - 1; i++) {
					rowData.push('')
				}

				if (rowSpan > 1) {
					for (let r = 1; r < rowSpan; r++) {
						rowSpanFills.push({ rowIndex: rowIndex + r, colIndex: actualCol, colSpan })
					}
				}

				actualCol += colSpan
			})

			acc.push(rowData)
			return acc
		}, [])

		// fill rowspan gaps in the rows below
		rowSpanFills.forEach(({ rowIndex, colIndex, colSpan }) => {
			if (matrix[rowIndex]) {
				matrix[rowIndex].splice(colIndex, 0, ...Array(colSpan).fill(''))
			}
		})

		return matrix.map((row) => row.join(',')).join('\n')
	}

	const valueFor = (format: Format): string => {
		if (format === 'Markdown') return raw
		if (format === 'HTML') return toHtml()
		return toCsv()
	}

	const download = (format: Format) => {
		const value = valueFor(format)
		if (format === 'Markdown') save('table.md', value, 'text/markdown')
		else if (format === 'HTML') save('table.html', value, 'text/html')
		else save('table.csv', value, 'text/csv')
		downloadOpen = false
	}

	const copy = async (format: Format) => {
		await navigator.clipboard.writeText(valueFor(format))
		copyOpen = false
		copied = true
		if (copyTimer) clearTimeout(copyTimer)
		copyTimer = setTimeout(() => (copied = false), 2000)
	}

	const formats: Format[] = ['Markdown', 'HTML', 'CSV']
</script>

<div data-streamdown-table-download class="ml-auto flex items-center justify-end gap-2 p-1">
	<button
		bind:this={downloadAnchor}
		class={streamdown.theme.components.button}
		onclick={() => (downloadOpen = !downloadOpen)}
		title="download table"
		aria-label="download table"
		type="button"
	>
		<span class="h-4 w-4" aria-hidden="true" {@attach attachSvg(downloadIcon)}></span>
	</button>
	<button
		bind:this={copyAnchor}
		class={streamdown.theme.components.button}
		onclick={() => (copyOpen = !copyOpen)}
		title="copy table"
		aria-label={copied ? 'copied' : 'copy table'}
		type="button"
	>
		<span class="h-4 w-4" aria-hidden="true" {@attach attachSvg(copied ? checkIcon : copyIcon)}
		></span>
	</button>
</div>

<PopupMenu
	open={downloadOpen}
	anchorEl={downloadAnchor}
	onClose={() => (downloadOpen = false)}
	estimatedHeight={160}
>
	{#each formats as format (format)}
		<MenuItem onclick={() => download(format)}>{format}</MenuItem>
	{/each}
</PopupMenu>

<PopupMenu
	open={copyOpen}
	anchorEl={copyAnchor}
	onClose={() => (copyOpen = false)}
	estimatedHeight={160}
>
	{#each formats as format (format)}
		<MenuItem onclick={() => void copy(format)}>{format}</MenuItem>
	{/each}
</PopupMenu>

<style>
	/* the table wrapper that follows the controls has my-4; drop its top margin so the
	   controls sit tight against the table, matching native streamdown */
	:global([data-streamdown-table-download] + div) {
		margin-top: 0px;
	}
</style>
