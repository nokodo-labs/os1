<script lang="ts">
	import { liquidGlass } from '$lib/liquid-glass/a/action'
	import LiquidGlassFilter from '$lib/liquid-glass/b/LiquidGlassFilter.svelte'

	const BG_IMAGE = 'https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?w=1200&q=80'

	// --- tunable parameters (slider-driven) ---
	let bezelWidth = $state(28)
	let thickness = $state(18)
	let refractionStrength = $state(1.0)
	let blurRadius = $state(8)
	let specularOpacity = $state(0.4)
	let specularAngle = $state(315)
	let glassBgOpacity = $state(0.12)
	let cornerRadius = $state(24)

	// version b SVG filter IDs + sizes
	const pillFilterId = 'lg-b-pill'
	const btnFilterId = 'lg-b-btn'
	const panelFilterId = 'lg-b-panel'
	const dragFilterId = 'lg-b-drag'

	const pillW = 420
	const pillH = 52
	const btnW = 150
	const btnH = 44
	const panelW = 380
	const panelH = 130
	const dragW = 200
	const dragH = 200

	// pill always uses its own half-height radius for true pill shape
	const pillRadius = $derived(Math.min(pillW, pillH) / 2)

	// draggable glass container state (version A)
	let dragAX = $state(40)
	let dragAY = $state(340)
	let draggingA = $state(false)
	let dragAOffsetX = 0
	let dragAOffsetY = 0

	// draggable glass container state (version B)
	let dragBX = $state(40)
	let dragBY = $state(340)
	let draggingB = $state(false)
	let dragBOffsetX = 0
	let dragBOffsetY = 0

	function startDrag(
		e: PointerEvent,
		setDragging: (v: boolean) => void,
		setOffset: (ox: number, oy: number) => void
	) {
		setDragging(true)
		const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
		setOffset(e.clientX - rect.left, e.clientY - rect.top)
		;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
	}

	function moveDrag(
		e: PointerEvent,
		isDragging: boolean,
		offsetX: number,
		offsetY: number,
		setPos: (x: number, y: number) => void,
		containerW: number,
		containerH: number
	) {
		if (!isDragging) return
		const parent = (e.currentTarget as HTMLElement).parentElement!
		const pr = parent.getBoundingClientRect()
		setPos(
			Math.max(0, Math.min(e.clientX - pr.left - offsetX, pr.width - containerW)),
			Math.max(0, Math.min(e.clientY - pr.top - offsetY, pr.height - containerH))
		)
	}
</script>

<svelte:head>
	<title>liquid glass lab</title>
</svelte:head>

<!-- version B SVG filters (reactive to slider values) -->
<LiquidGlassFilter
	filterId={pillFilterId}
	width={pillW}
	height={pillH}
	cornerRadius={pillRadius}
	{bezelWidth}
	{thickness}
	{refractionStrength}
	{blurRadius}
	{specularOpacity}
	{specularAngle}
	{glassBgOpacity}
/>
<LiquidGlassFilter
	filterId={btnFilterId}
	width={btnW}
	height={btnH}
	{cornerRadius}
	{bezelWidth}
	{thickness}
	{refractionStrength}
	{blurRadius}
	{specularOpacity}
	{specularAngle}
	{glassBgOpacity}
/>
<LiquidGlassFilter
	filterId={panelFilterId}
	width={panelW}
	height={panelH}
	{cornerRadius}
	{bezelWidth}
	{thickness}
	{refractionStrength}
	{blurRadius}
	{specularOpacity}
	{specularAngle}
	{glassBgOpacity}
/>
<LiquidGlassFilter
	filterId={dragFilterId}
	width={dragW}
	height={dragH}
	{cornerRadius}
	{bezelWidth}
	{thickness}
	{refractionStrength}
	{blurRadius}
	{specularOpacity}
	{specularAngle}
	{glassBgOpacity}
/>

<div class="flex h-dvh w-full flex-col overflow-auto lg:flex-row">
	<!-- left half: version A -->
	<section class="relative min-h-80 flex-1 border-b border-white/10 lg:border-r lg:border-b-0">
		<div class="absolute top-3 left-4 z-30">
			<div class="rounded-full bg-black/50 px-3 py-1.5 text-xs font-medium text-white/80">
				version a - css action
			</div>
		</div>

		<img
			src={BG_IMAGE}
			alt="background for glass demo"
			class="absolute inset-0 h-full w-full object-cover"
			draggable="false"
		/>

		<!-- fixed glass elements -->
		<div class="pointer-events-none absolute inset-0 z-10 p-5 pt-12">
			<div class="pointer-events-auto grid gap-3">
				<div
					use:liquidGlass={'nav'}
					class="w-full max-w-md rounded-full px-5 py-3 text-sm text-white/90"
				>
					navigation pill
				</div>
				<div class="flex gap-3">
					<button
						type="button"
						use:liquidGlass={'subtle'}
						class="rounded-2xl px-4 py-2.5 text-xs text-white/85"
					>
						subtle button
					</button>
					<button
						type="button"
						use:liquidGlass={'heavy'}
						class="rounded-2xl px-4 py-2.5 text-xs text-white/85"
					>
						heavy button
					</button>
				</div>
				<div
					use:liquidGlass={'panel'}
					class="max-w-sm rounded-3xl px-5 py-4 text-xs text-white/80"
				>
					<div class="font-medium text-white/90">glass panel</div>
					<div class="mt-1.5 text-white/60">focus the input to see state change</div>
					<input
						class="mt-2.5 w-full rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/80 outline-none"
						placeholder="type here"
					/>
				</div>
			</div>
		</div>

		<!-- draggable A -->
		<div
			class="absolute z-20 cursor-grab rounded-3xl select-none active:cursor-grabbing"
			style="left: {dragAX}px; top: {dragAY}px; width: {dragW}px; height: {dragH}px;"
			role="slider"
			tabindex="-1"
			aria-label="draggable glass pane"
			aria-valuemin={0}
			aria-valuemax={100}
			aria-valuenow={50}
			onpointerdown={(e) =>
				startDrag(
					e,
					(v) => (draggingA = v),
					(ox, oy) => {
						dragAOffsetX = ox
						dragAOffsetY = oy
					}
				)}
			onpointermove={(e) =>
				moveDrag(
					e,
					draggingA,
					dragAOffsetX,
					dragAOffsetY,
					(x, y) => {
						dragAX = x
						dragAY = y
					},
					dragW,
					dragH
				)}
			onpointerup={() => (draggingA = false)}
			onpointercancel={() => (draggingA = false)}
		>
			<div
				use:liquidGlass={'heavy'}
				class="grid h-full w-full place-items-center rounded-3xl text-xs text-white/70"
			>
				drag me
			</div>
		</div>
	</section>

	<!-- right half: version B -->
	<section class="relative min-h-80 flex-1">
		<div class="absolute top-3 left-4 z-30">
			<div class="rounded-full bg-black/50 px-3 py-1.5 text-xs font-medium text-white/80">
				version b - svg displacement
			</div>
		</div>

		<img
			src={BG_IMAGE}
			alt="background for glass demo"
			class="absolute inset-0 h-full w-full object-cover"
			draggable="false"
		/>

		<!-- fixed glass elements (same layout as A) -->
		<div class="pointer-events-none absolute inset-0 z-10 p-5 pt-12">
			<div class="pointer-events-auto grid gap-3">
				<div
					class="flex items-center px-5 text-sm text-white/90"
					style="width: {pillW}px; height: {pillH}px; border-radius: {pillRadius}px; backdrop-filter: url(#{pillFilterId}); -webkit-backdrop-filter: url(#{pillFilterId});"
				>
					navigation pill
				</div>
				<div class="flex gap-3">
					<div
						class="grid place-items-center text-xs text-white/85"
						style="width: {btnW}px; height: {btnH}px; border-radius: {cornerRadius}px; backdrop-filter: url(#{btnFilterId}); -webkit-backdrop-filter: url(#{btnFilterId});"
					>
						subtle button
					</div>
					<div
						class="grid place-items-center text-xs text-white/85"
						style="width: {btnW}px; height: {btnH}px; border-radius: {cornerRadius}px; backdrop-filter: url(#{btnFilterId}); -webkit-backdrop-filter: url(#{btnFilterId});"
					>
						heavy button
					</div>
				</div>
				<div
					class="px-5 py-4 text-xs text-white/80"
					style="width: {panelW}px; height: {panelH}px; border-radius: {cornerRadius}px; backdrop-filter: url(#{panelFilterId}); -webkit-backdrop-filter: url(#{panelFilterId});"
				>
					<div class="font-medium text-white/90">glass panel</div>
					<div class="mt-1.5 text-white/60">focus the input to see state change</div>
					<input
						class="mt-2.5 w-full rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/80 outline-none"
						placeholder="type here"
					/>
				</div>
			</div>
		</div>

		<!-- draggable B -->
		<div
			class="absolute z-20 cursor-grab select-none active:cursor-grabbing"
			style="left: {dragBX}px; top: {dragBY}px; width: {dragW}px; height: {dragH}px; border-radius: {cornerRadius}px; backdrop-filter: url(#{dragFilterId}); -webkit-backdrop-filter: url(#{dragFilterId});"
			role="slider"
			tabindex="-1"
			aria-label="draggable glass pane"
			aria-valuemin={0}
			aria-valuemax={100}
			aria-valuenow={50}
			onpointerdown={(e) =>
				startDrag(
					e,
					(v) => (draggingB = v),
					(ox, oy) => {
						dragBOffsetX = ox
						dragBOffsetY = oy
					}
				)}
			onpointermove={(e) =>
				moveDrag(
					e,
					draggingB,
					dragBOffsetX,
					dragBOffsetY,
					(x, y) => {
						dragBX = x
						dragBY = y
					},
					dragW,
					dragH
				)}
			onpointerup={() => (draggingB = false)}
			onpointercancel={() => (draggingB = false)}
		>
			<div class="grid h-full w-full place-items-center text-xs text-white/70">drag me</div>
		</div>

		<!-- controls panel -->
		<div
			class="absolute right-3 bottom-3 z-30 w-72 rounded-2xl border border-white/10 bg-black/80 p-4 backdrop-blur-md"
		>
			<div class="mb-3 text-xs font-semibold tracking-wider text-white/70 uppercase">
				version b controls
			</div>
			<div class="grid gap-2.5 text-xs text-white/80">
				<!-- corner radius -->
				<label class="flex items-center gap-2">
					<span class="w-28 shrink-0 text-white/60">corner radius</span>
					<input
						type="range"
						min="4"
						max="100"
						step="1"
						bind:value={cornerRadius}
						class="flex-1"
					/>
					<span class="w-8 text-right font-mono text-white/50">{cornerRadius}</span>
				</label>

				<!-- bezel width -->
				<label class="flex items-center gap-2">
					<span class="w-28 shrink-0 text-white/60">bezel width</span>
					<input
						type="range"
						min="4"
						max="80"
						step="1"
						bind:value={bezelWidth}
						class="flex-1"
					/>
					<span class="w-8 text-right font-mono text-white/50">{bezelWidth}</span>
				</label>

				<!-- glass thickness -->
				<label class="flex items-center gap-2">
					<span class="w-28 shrink-0 text-white/60">glass thickness</span>
					<input
						type="range"
						min="1"
						max="60"
						step="1"
						bind:value={thickness}
						class="flex-1"
					/>
					<span class="w-8 text-right font-mono text-white/50">{thickness}</span>
				</label>

				<!-- refraction strength -->
				<label class="flex items-center gap-2">
					<span class="w-28 shrink-0 text-white/60">refraction</span>
					<input
						type="range"
						min="0"
						max="5"
						step="0.1"
						bind:value={refractionStrength}
						class="flex-1"
					/>
					<span class="w-8 text-right font-mono text-white/50"
						>{refractionStrength.toFixed(1)}</span
					>
				</label>

				<!-- blur radius -->
				<label class="flex items-center gap-2">
					<span class="w-28 shrink-0 text-white/60">blur radius</span>
					<input
						type="range"
						min="0"
						max="40"
						step="0.5"
						bind:value={blurRadius}
						class="flex-1"
					/>
					<span class="w-8 text-right font-mono text-white/50"
						>{blurRadius.toFixed(1)}</span
					>
				</label>

				<!-- specular opacity -->
				<label class="flex items-center gap-2">
					<span class="w-28 shrink-0 text-white/60">specular opacity</span>
					<input
						type="range"
						min="0"
						max="1"
						step="0.01"
						bind:value={specularOpacity}
						class="flex-1"
					/>
					<span class="w-8 text-right font-mono text-white/50"
						>{specularOpacity.toFixed(2)}</span
					>
				</label>

				<!-- specular angle -->
				<label class="flex items-center gap-2">
					<span class="w-28 shrink-0 text-white/60">specular angle</span>
					<input
						type="range"
						min="0"
						max="360"
						step="5"
						bind:value={specularAngle}
						class="flex-1"
					/>
					<span class="w-8 text-right font-mono text-white/50">{specularAngle}</span>
				</label>

				<!-- glass bg opacity -->
				<label class="flex items-center gap-2">
					<span class="w-28 shrink-0 text-white/60">glass bg opacity</span>
					<input
						type="range"
						min="0"
						max="0.5"
						step="0.01"
						bind:value={glassBgOpacity}
						class="flex-1"
					/>
					<span class="w-8 text-right font-mono text-white/50"
						>{glassBgOpacity.toFixed(2)}</span
					>
				</label>
			</div>
		</div>
	</section>
</div>
