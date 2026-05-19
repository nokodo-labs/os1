<script lang="ts">
	import { portal } from '$lib/actions/portal'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { SvelteMap } from 'svelte/reactivity'

	interface Props {
		open: boolean
		src: string
		alt?: string
		fileId?: string | null
		onClose: () => void
	}

	let { open, src, alt = 'image preview', fileId = null, onClose }: Props = $props()

	// zoom/pan state
	let scale = $state(1)
	let translateX = $state(0)
	let translateY = $state(0)
	let isPanning = $state(false)
	let isPinching = $state(false)
	let panStart = $state({ x: 0, y: 0 })
	let panOrigin = $state({ x: 0, y: 0 })
	let pinchStartDistance = 0
	let pinchStartScale = 1
	let pinchStartCenter = { x: 0, y: 0 }
	let pinchStartTranslate = { x: 0, y: 0 }
	const activePointers = new SvelteMap<number, { x: number; y: number }>()

	const MIN_SCALE = 1
	const MAX_SCALE = 8
	const PAN_MARGIN = 80 // px of image that must always remain visible

	let imgEl: HTMLImageElement | null = $state(null)

	function resetTransform() {
		scale = 1
		translateX = 0
		translateY = 0
		isPanning = false
		isPinching = false
		activePointers.clear()
	}

	function clampPan(tx: number, ty: number, targetScale = scale): { x: number; y: number } {
		if (!imgEl) return { x: tx, y: ty }
		const vw = window.innerWidth
		const vh = window.innerHeight
		const iw = imgEl.offsetWidth * targetScale
		const ih = imgEl.offsetHeight * targetScale
		const maxTx = vw / 2 + iw / 2 - PAN_MARGIN
		const minTx = -(vw / 2 + iw / 2 - PAN_MARGIN)
		const maxTy = vh / 2 + ih / 2 - PAN_MARGIN
		const minTy = -(vh / 2 + ih / 2 - PAN_MARGIN)
		return {
			x: Math.max(minTx, Math.min(maxTx, tx)),
			y: Math.max(minTy, Math.min(maxTy, ty)),
		}
	}

	function pointerValues(): Array<{ x: number; y: number }> {
		return [...activePointers.values()]
	}

	function pointerDistance(points: Array<{ x: number; y: number }>): number {
		const first = points[0]
		const second = points[1]
		if (!first || !second) return 0
		return Math.hypot(second.x - first.x, second.y - first.y)
	}

	function pointerCenter(points: Array<{ x: number; y: number }>): { x: number; y: number } {
		const first = points[0]
		const second = points[1]
		if (!first || !second) return { x: 0, y: 0 }
		return { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 }
	}

	function localPoint(
		element: HTMLElement,
		point: { x: number; y: number }
	): { x: number; y: number } {
		const rect = element.getBoundingClientRect()
		return {
			x: point.x - rect.left - rect.width / 2,
			y: point.y - rect.top - rect.height / 2,
		}
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
		const nextPan = clampPan(
			cx - factor * (cx - translateX),
			cy - factor * (cy - translateY),
			next
		)
		translateX = nextPan.x
		translateY = nextPan.y
		scale = next
	}

	function handlePointerDown(e: PointerEvent) {
		e.preventDefault()
		const element = e.currentTarget as HTMLElement
		activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
		element.setPointerCapture(e.pointerId)

		if (activePointers.size >= 2) {
			const points = pointerValues()
			isPanning = false
			isPinching = true
			pinchStartDistance = pointerDistance(points)
			pinchStartScale = scale
			pinchStartCenter = localPoint(element, pointerCenter(points))
			pinchStartTranslate = { x: translateX, y: translateY }
			return
		}

		if (scale > 1) {
			isPanning = true
			panStart = { x: e.clientX, y: e.clientY }
			panOrigin = { x: translateX, y: translateY }
		}
	}

	function handlePointerMove(e: PointerEvent) {
		if (!activePointers.has(e.pointerId)) return
		e.preventDefault()
		activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY })

		if (isPinching && activePointers.size >= 2) {
			const element = e.currentTarget as HTMLElement
			const points = pointerValues()
			const currentDistance = pointerDistance(points)
			if (pinchStartDistance <= 0 || currentDistance <= 0) return
			const currentCenter = localPoint(element, pointerCenter(points))
			const next = Math.min(
				MAX_SCALE,
				Math.max(MIN_SCALE, pinchStartScale * (currentDistance / pinchStartDistance))
			)
			if (next <= MIN_SCALE) {
				scale = MIN_SCALE
				translateX = 0
				translateY = 0
				return
			}
			const factor = next / pinchStartScale
			const nextPan = clampPan(
				currentCenter.x - factor * (pinchStartCenter.x - pinchStartTranslate.x),
				currentCenter.y - factor * (pinchStartCenter.y - pinchStartTranslate.y),
				next
			)
			translateX = nextPan.x
			translateY = nextPan.y
			scale = next
			return
		}

		if (!isPanning) return
		const rawTx = panOrigin.x + (e.clientX - panStart.x)
		const rawTy = panOrigin.y + (e.clientY - panStart.y)
		const nextPan = clampPan(rawTx, rawTy)
		translateX = nextPan.x
		translateY = nextPan.y
	}

	function handlePointerUp(e: PointerEvent) {
		activePointers.delete(e.pointerId)
		try {
			;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
		} catch {
			// pointer capture may already be gone after browser gestures are cancelled.
		}

		if (activePointers.size >= 2) return
		if (activePointers.size === 1 && scale > 1) {
			const point = pointerValues()[0]
			if (point) {
				isPinching = false
				isPanning = true
				panStart = point
				panOrigin = { x: translateX, y: translateY }
				return
			}
		}
		isPanning = false
		isPinching = false
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
			const nextPan = clampPan(
				cx - factor * (cx - translateX),
				cy - factor * (cy - translateY),
				next
			)
			translateX = nextPan.x
			translateY = nextPan.y
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

	function openFileDetails(e: MouseEvent): void {
		e.stopPropagation()
		if (!fileId) return
		onClose()
		queueMicrotask(() => modals.open('file-details', { fileId }))
	}

	// reset transform when lightbox opens/closes
	$effect(() => {
		if (open) resetTransform()
	})
</script>

{#if open}
	<div use:portal>
		<div
			class="fixed inset-0 z-10000 flex items-center justify-center bg-black/85 backdrop-blur-sm"
			style="touch-action: none; overscroll-behavior: contain;"
			role="dialog"
			aria-label="image preview"
			aria-modal="true"
			tabindex="-1"
			onclick={handleBackdropClick}
			onkeydown={handleKeyDown}
		>
			<div class="absolute top-4 right-4 z-10 flex items-center gap-2">
				{#if fileId}
					<button
						type="button"
						class="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border-none bg-transparent text-white/80 transition-all duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
						aria-label="open file details"
						title="file details"
						onclick={openFileDetails}
					>
						<InfoCircle class="h-5 w-5" />
					</button>
				{/if}
				<button
					type="button"
					class="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border-none bg-transparent text-white/80 transition-all duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
					aria-label="close preview"
					onclick={(e) => {
						e.stopPropagation()
						onClose()
					}}
				>
					<XMark class="h-5 w-5" />
				</button>
			</div>

			<!-- zoom/pan container — fills the backdrop so the image is truly fullscreen-centered -->
			<div
				class="absolute inset-0 flex items-center justify-center"
				style="cursor: {scale > 1
					? isPanning
						? 'grabbing'
						: 'grab'
					: 'zoom-in'}; touch-action: none; overscroll-behavior: contain;"
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
					bind:this={imgEl}
					{src}
					{alt}
					class="max-h-[90vh] max-w-[90vw] rounded-lg object-contain shadow-2xl select-none"
					style="transform: scale({scale}) translate({translateX / scale}px, {translateY /
						scale}px); transition: {isPanning || isPinching
						? 'none'
						: 'transform 0.2s ease'}; touch-action: none;"
					draggable="false"
					role="presentation"
				/>
			</div>
		</div>
	</div>
{/if}
