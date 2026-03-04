<script lang="ts">
	import { portal } from '$lib/actions/portal'
	import XMark from '$lib/components/icons/XMark.svelte'

	interface Props {
		open: boolean
		src: string
		alt?: string
		onClose: () => void
	}

	let { open, src, alt = 'image preview', onClose }: Props = $props()

	// zoom/pan state
	let scale = $state(1)
	let translateX = $state(0)
	let translateY = $state(0)
	let isPanning = $state(false)
	let panStart = $state({ x: 0, y: 0 })
	let panOrigin = $state({ x: 0, y: 0 })

	const MIN_SCALE = 1
	const MAX_SCALE = 8

	function resetTransform() {
		scale = 1
		translateX = 0
		translateY = 0
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			if (scale > 1) {
				resetTransform()
			} else {
				onClose()
			}
		}
	}

	function handleWheel(e: WheelEvent) {
		e.preventDefault()
		const delta = e.deltaY > 0 ? 0.9 : 1.1
		const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale * delta))
		if (next <= MIN_SCALE) {
			resetTransform()
			return
		}
		// zoom toward cursor position
		const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
		const cx = e.clientX - rect.left - rect.width / 2
		const cy = e.clientY - rect.top - rect.height / 2
		const factor = next / scale
		translateX = cx - factor * (cx - translateX)
		translateY = cy - factor * (cy - translateY)
		scale = next
	}

	function handlePointerDown(e: PointerEvent) {
		if (scale <= 1) return
		e.preventDefault()
		isPanning = true
		panStart = { x: e.clientX, y: e.clientY }
		panOrigin = { x: translateX, y: translateY }
		;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
	}

	function handlePointerMove(e: PointerEvent) {
		if (!isPanning) return
		translateX = panOrigin.x + (e.clientX - panStart.x)
		translateY = panOrigin.y + (e.clientY - panStart.y)
	}

	function handlePointerUp() {
		isPanning = false
	}

	function handleDoubleClick(e: MouseEvent) {
		e.stopPropagation()
		if (scale > 1) {
			resetTransform()
		} else {
			// zoom to 3x toward click position
			const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
			const cx = e.clientX - rect.left - rect.width / 2
			const cy = e.clientY - rect.top - rect.height / 2
			const next = 3
			const factor = next / scale
			translateX = cx - factor * (cx - translateX)
			translateY = cy - factor * (cy - translateY)
			scale = next
		}
	}

	function handleBackdropClick() {
		if (scale > 1) {
			resetTransform()
		} else {
			onClose()
		}
	}

	// reset transform when lightbox opens/closes
	$effect(() => {
		if (open) resetTransform()
	})
</script>

{#if open}
	<div use:portal>
		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<div
			class="fixed inset-0 z-10000 flex items-center justify-center bg-black/85 backdrop-blur-sm"
			role="dialog"
			aria-label="image preview"
			aria-modal="true"
			tabindex="-1"
			onclick={handleBackdropClick}
			onkeydown={handleKeyDown}
		>
			<button
				type="button"
				class="absolute top-4 right-4 z-10 flex h-10 w-10 cursor-pointer items-center justify-center rounded-full bg-white/10 text-white/80 backdrop-blur-sm transition-colors hover:bg-white/20 hover:text-white"
				aria-label="close preview"
				onclick={onClose}
			>
				<XMark class="h-5 w-5" />
			</button>

			<!-- zoom/pan container -->
			<div
				class="flex max-h-[90vh] max-w-[90vw] items-center justify-center overflow-hidden"
				style="cursor: {scale > 1 ? (isPanning ? 'grabbing' : 'grab') : 'zoom-in'};"
				role="presentation"
				onwheel={handleWheel}
				onpointerdown={handlePointerDown}
				onpointermove={handlePointerMove}
				onpointerup={handlePointerUp}
				onpointercancel={handlePointerUp}
				ondblclick={handleDoubleClick}
				onclick={(e) => e.stopPropagation()}
				onkeydown={(e) => e.stopPropagation()}
			>
				<img
					{src}
					{alt}
					class="max-h-[90vh] max-w-[90vw] rounded-lg object-contain shadow-2xl select-none"
					style="transform: scale({scale}) translate({translateX / scale}px, {translateY /
						scale}px); transition: {isPanning ? 'none' : 'transform 0.2s ease'};"
					draggable="false"
					role="presentation"
				/>
			</div>
		</div>
	</div>
{/if}
