<script lang="ts">
	import { liquidGlass } from '$lib/liquid-glass/a/action'

	const BG_IMAGE = 'https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?w=1200&q=80'

	const dragW = 200
	const dragH = 200
	let dragX = $state(40)
	let dragY = $state(260)
	let dragging = $state(false)
	let dragOffsetX = 0
	let dragOffsetY = 0

	function startDrag(e: PointerEvent) {
		if (!(e.currentTarget instanceof HTMLElement)) return
		dragging = true
		const rect = e.currentTarget.getBoundingClientRect()
		dragOffsetX = e.clientX - rect.left
		dragOffsetY = e.clientY - rect.top
		e.currentTarget.setPointerCapture(e.pointerId)
	}

	function moveDrag(e: PointerEvent) {
		if (!dragging) return
		const parent = e.currentTarget instanceof HTMLElement ? e.currentTarget.parentElement : null
		if (!parent) return
		const pr = parent.getBoundingClientRect()
		dragX = Math.max(0, Math.min(e.clientX - pr.left - dragOffsetX, pr.width - dragW))
		dragY = Math.max(0, Math.min(e.clientY - pr.top - dragOffsetY, pr.height - dragH))
	}

	function stopDrag(e: PointerEvent) {
		dragging = false
		if (e.currentTarget instanceof HTMLElement) {
			e.currentTarget.releasePointerCapture(e.pointerId)
		}
	}
</script>

<svelte:head>
	<title>liquid glass - css action</title>
</svelte:head>

<section class="relative min-h-dvh w-full overflow-hidden">
	<div class="absolute top-3 left-4 z-30">
		<div class="rounded-full bg-black/60 px-3 py-1.5 text-xs font-medium text-foreground/80">
			css action demo
		</div>
	</div>

	<img
		src={BG_IMAGE}
		alt="background for glass demo"
		class="absolute inset-0 h-full w-full object-cover"
		draggable="false"
	/>

	<div class="pointer-events-none absolute inset-0 z-10 p-6 pt-14">
		<div class="pointer-events-auto grid gap-3">
			<div
				use:liquidGlass={'nav'}
				class="w-full max-w-md rounded-full px-5 py-3 text-sm text-foreground/90"
			>
				navigation pill
			</div>
			<div class="flex gap-3">
				<button
					type="button"
					use:liquidGlass={'subtle'}
					class="rounded-2xl px-4 py-2.5 text-xs text-foreground/85"
				>
					subtle button
				</button>
				<button
					type="button"
					use:liquidGlass={'heavy'}
					class="rounded-2xl px-4 py-2.5 text-xs text-foreground/85"
				>
					heavy button
				</button>
			</div>
			<div
				use:liquidGlass={'panel'}
				class="max-w-sm rounded-3xl px-5 py-4 text-xs text-foreground/80"
			>
				<div class="font-medium text-foreground/90">glass panel</div>
				<div class="mt-1.5 text-foreground/60">focus the input to see state change</div>
				<input
					class="mt-2.5 w-full rounded-2xl border border-foreground/10 bg-foreground/5 px-3 py-2 text-xs text-foreground/80 outline-none"
					placeholder="type here"
				/>
			</div>
		</div>
	</div>

	<div
		class="absolute z-20 cursor-grab rounded-3xl select-none active:cursor-grabbing"
		style="left: {dragX}px; top: {dragY}px; width: {dragW}px; height: {dragH}px;"
		role="slider"
		tabindex="-1"
		aria-label="draggable glass pane"
		aria-valuemin={0}
		aria-valuemax={100}
		aria-valuenow={50}
		onpointerdown={startDrag}
		onpointermove={moveDrag}
		onpointerup={stopDrag}
		onpointercancel={stopDrag}
	>
		<div
			use:liquidGlass={'heavy'}
			class="grid h-full w-full place-items-center rounded-3xl text-xs text-foreground/70"
		>
			drag me
		</div>
	</div>
</section>
