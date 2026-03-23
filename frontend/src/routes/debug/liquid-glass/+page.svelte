<script lang="ts">
	import { Slider, Switch } from '$lib/components/primitives'
	import { SearchBar } from '$lib/components/primitives/liquid-glass'
	import LiquidGlassFilter from '$lib/liquid-glass/b/LiquidGlassFilter.svelte'

	const BG_IMAGE = 'https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?w=1200&q=80'

	// tunable parameters (slider-driven, matching LiquidGlassFilter defaults)
	let bezelWidth = $state(44)
	let thickness = $state(33)
	let glassThickness = $state(140)
	let refractionStrength = $state(1.8)
	let innerRefraction = $state(0)
	let blurRadius = $state(0.3)
	let specularOpacity = $state(1.0)
	let specularSaturation = $state(4)
	let specularAngle = $state(315)
	let cornerRadius = $state(24)
	let chromaticAberration = $state(0.13)
	let glassTint = $state(0.08)

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

	// draggable glass container state (version B)
	let dragBX = $state(40)
	let dragBY = $state(340)
	let draggingB = $state(false)
	let dragBOffsetX = 0
	let dragBOffsetY = 0

	// liquid switch/slider demo state
	let switchChecked = $state(false)
	let sliderValue = $state(50)
	let searchQuery = $state('')

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
	{glassThickness}
	{refractionStrength}
	{innerRefraction}
	{blurRadius}
	{specularOpacity}
	{specularSaturation}
	{specularAngle}
	{chromaticAberration}
	{glassTint}
/>
<LiquidGlassFilter
	filterId={btnFilterId}
	width={btnW}
	height={btnH}
	{cornerRadius}
	{bezelWidth}
	{thickness}
	{glassThickness}
	{refractionStrength}
	{innerRefraction}
	{blurRadius}
	{specularOpacity}
	{specularSaturation}
	{specularAngle}
	{chromaticAberration}
	{glassTint}
/>
<LiquidGlassFilter
	filterId={panelFilterId}
	width={panelW}
	height={panelH}
	{cornerRadius}
	{bezelWidth}
	{thickness}
	{glassThickness}
	{refractionStrength}
	{innerRefraction}
	{blurRadius}
	{specularOpacity}
	{specularSaturation}
	{specularAngle}
	{chromaticAberration}
	{glassTint}
/>
<LiquidGlassFilter
	filterId={dragFilterId}
	width={dragW}
	height={dragH}
	{cornerRadius}
	{bezelWidth}
	{thickness}
	{glassThickness}
	{refractionStrength}
	{innerRefraction}
	{blurRadius}
	{specularOpacity}
	{specularSaturation}
	{specularAngle}
	{chromaticAberration}
	{glassTint}
/>

<div class="flex h-dvh w-full flex-col overflow-auto lg:flex-row">
	<!-- left half: liquid glass components on transparent background (webgl behind) -->
	<section
		class="border-foreground/10 relative min-h-80 flex-1 overflow-hidden border-b lg:border-r lg:border-b-0"
	>
		<div class="absolute top-3 left-4 z-30">
			<div
				class="text-foreground/80 rounded-full bg-black/50 px-3 py-1.5 text-xs font-medium"
			>
				liquid glass components
			</div>
		</div>

		<div
			class="relative z-10 flex h-full w-full flex-col items-center justify-center gap-12 px-8 py-16"
		>
			<div class="grid gap-3 text-center">
				<div class="text-foreground/60 text-xs font-semibold tracking-wider uppercase">
					search bar
				</div>
				<SearchBar bind:value={searchQuery} width={340} height={48} />
				<div class="text-foreground/50 text-xs">
					{searchQuery || 'type to search...'}
				</div>
			</div>

			<div class="grid gap-3 text-center">
				<div class="text-foreground/60 text-xs font-semibold tracking-wider uppercase">
					switch
				</div>
				<Switch size="lg" bind:checked={switchChecked} />
				<div class="text-foreground/50 text-xs">
					{switchChecked ? 'on' : 'off'}
				</div>
			</div>

			<div class="grid gap-3 text-center">
				<div class="text-foreground/60 text-xs font-semibold tracking-wider uppercase">
					slider
				</div>
				<Slider size="md" bind:value={sliderValue} />
				<div class="text-foreground/50 text-xs">
					{sliderValue}
				</div>
			</div>

			<div class="grid gap-3 text-center">
				<div class="text-foreground/60 text-xs font-semibold tracking-wider uppercase">
					switch sizes
				</div>
				<div class="flex items-center gap-6">
					<Switch size="sm" checked={true} />
					<Switch size="md" />
					<Switch size="lg" checked={true} />
				</div>
			</div>
		</div>
	</section>

	<!-- right half: version B -->
	<section class="relative min-h-80 flex-1 overflow-hidden">
		<div class="absolute top-3 left-4 z-30">
			<div
				class="text-foreground/80 rounded-full bg-black/50 px-3 py-1.5 text-xs font-medium"
			>
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
					class="text-foreground/90 flex items-center px-5 text-sm"
					style="width: {pillW}px; height: {pillH}px; border-radius: {pillRadius}px; backdrop-filter: url(#{pillFilterId}); -webkit-backdrop-filter: url(#{pillFilterId});"
				>
					navigation pill
				</div>
				<div class="flex gap-3">
					<div
						class="text-foreground/85 grid place-items-center text-xs"
						style="width: {btnW}px; height: {btnH}px; border-radius: {cornerRadius}px; backdrop-filter: url(#{btnFilterId}); -webkit-backdrop-filter: url(#{btnFilterId});"
					>
						subtle button
					</div>
					<div
						class="text-foreground/85 grid place-items-center text-xs"
						style="width: {btnW}px; height: {btnH}px; border-radius: {cornerRadius}px; backdrop-filter: url(#{btnFilterId}); -webkit-backdrop-filter: url(#{btnFilterId});"
					>
						heavy button
					</div>
				</div>
				<div
					class="text-foreground/80 px-5 py-4 text-xs"
					style="width: {panelW}px; height: {panelH}px; border-radius: {cornerRadius}px; backdrop-filter: url(#{panelFilterId}); -webkit-backdrop-filter: url(#{panelFilterId});"
				>
					<div class="text-foreground/90 font-medium">glass panel</div>
					<div class="text-foreground/60 mt-1.5">focus the input to see state change</div>
					<input
						class="border-foreground/10 bg-foreground/5 text-foreground/80 mt-2.5 w-full rounded-2xl border px-3 py-2 text-xs outline-none"
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
			<div class="text-foreground/70 grid h-full w-full place-items-center text-xs">
				drag me
			</div>
		</div>

		<!-- controls panel -->
		<div
			class="border-foreground/10 absolute right-3 bottom-3 z-30 max-h-[calc(100%-24px)] w-72 overflow-y-auto rounded-2xl border bg-black/80 p-4 backdrop-blur-md"
		>
			<div class="text-foreground/70 mb-3 text-xs font-semibold tracking-wider uppercase">
				version b controls
			</div>
			<div class="text-foreground/80 grid gap-2.5 text-xs">
				<!-- corner radius -->
				<label class="flex items-center gap-2">
					<span class="text-foreground/60 w-28 shrink-0">corner radius</span>
					<input
						type="range"
						min="4"
						max="100"
						step="1"
						bind:value={cornerRadius}
						class="flex-1"
					/>
					<input
						type="number"
						min="4"
						max="100"
						step="1"
						bind:value={cornerRadius}
						class="border-foreground/10 bg-foreground/5 text-foreground/60 w-14 rounded border px-1.5 py-0.5 text-right font-mono outline-none"
					/>
				</label>

				<!-- bezel width -->
				<label class="flex items-center gap-2">
					<span class="text-foreground/60 w-28 shrink-0">bezel width</span>
					<input
						type="range"
						min="4"
						max="80"
						step="1"
						bind:value={bezelWidth}
						class="flex-1"
					/>
					<input
						type="number"
						min="4"
						max="80"
						step="1"
						bind:value={bezelWidth}
						class="border-foreground/10 bg-foreground/5 text-foreground/60 w-14 rounded border px-1.5 py-0.5 text-right font-mono outline-none"
					/>
				</label>

				<!-- glass thickness (bezel height) -->
				<label class="flex items-center gap-2">
					<span class="text-foreground/60 w-28 shrink-0">bezel height</span>
					<input
						type="range"
						min="1"
						max="60"
						step="1"
						bind:value={thickness}
						class="flex-1"
					/>
					<input
						type="number"
						min="1"
						max="60"
						step="1"
						bind:value={thickness}
						class="border-foreground/10 bg-foreground/5 text-foreground/60 w-14 rounded border px-1.5 py-0.5 text-right font-mono outline-none"
					/>
				</label>

				<!-- flat glass thickness -->
				<label class="flex items-center gap-2">
					<span class="text-foreground/60 w-28 shrink-0">glass thickness</span>
					<input
						type="range"
						min="0"
						max="200"
						step="1"
						bind:value={glassThickness}
						class="flex-1"
					/>
					<input
						type="number"
						min="0"
						max="200"
						step="1"
						bind:value={glassThickness}
						class="border-foreground/10 bg-foreground/5 text-foreground/60 w-14 rounded border px-1.5 py-0.5 text-right font-mono outline-none"
					/>
				</label>

				<!-- refraction strength -->
				<label class="flex items-center gap-2">
					<span class="text-foreground/60 w-28 shrink-0">refraction</span>
					<input
						type="range"
						min="0"
						max="3"
						step="0.05"
						bind:value={refractionStrength}
						class="flex-1"
					/>
					<input
						type="number"
						min="0"
						max="3"
						step="0.05"
						bind:value={refractionStrength}
						class="border-foreground/10 bg-foreground/5 text-foreground/60 w-14 rounded border px-1.5 py-0.5 text-right font-mono outline-none"
					/>
				</label>

				<!-- inner refraction -->
				<label class="flex items-center gap-2">
					<span class="text-foreground/60 w-28 shrink-0">inner refraction</span>
					<input
						type="range"
						min="0"
						max="0.5"
						step="0.01"
						bind:value={innerRefraction}
						class="flex-1"
					/>
					<input
						type="number"
						min="0"
						max="0.5"
						step="0.01"
						bind:value={innerRefraction}
						class="border-foreground/10 bg-foreground/5 text-foreground/60 w-14 rounded border px-1.5 py-0.5 text-right font-mono outline-none"
					/>
				</label>

				<!-- blur radius -->
				<label class="flex items-center gap-2">
					<span class="text-foreground/60 w-28 shrink-0">blur radius</span>
					<input
						type="range"
						min="0"
						max="10"
						step="0.1"
						bind:value={blurRadius}
						class="flex-1"
					/>
					<input
						type="number"
						min="0"
						max="10"
						step="0.1"
						bind:value={blurRadius}
						class="border-foreground/10 bg-foreground/5 text-foreground/60 w-14 rounded border px-1.5 py-0.5 text-right font-mono outline-none"
					/>
				</label>

				<!-- specular opacity -->
				<label class="flex items-center gap-2">
					<span class="text-foreground/60 w-28 shrink-0">specular opacity</span>
					<input
						type="range"
						min="0"
						max="1"
						step="0.01"
						bind:value={specularOpacity}
						class="flex-1"
					/>
					<input
						type="number"
						min="0"
						max="1"
						step="0.01"
						bind:value={specularOpacity}
						class="border-foreground/10 bg-foreground/5 text-foreground/60 w-14 rounded border px-1.5 py-0.5 text-right font-mono outline-none"
					/>
				</label>

				<!-- specular saturation -->
				<label class="flex items-center gap-2">
					<span class="text-foreground/60 w-28 shrink-0">saturation</span>
					<input
						type="range"
						min="1"
						max="20"
						step="0.5"
						bind:value={specularSaturation}
						class="flex-1"
					/>
					<input
						type="number"
						min="1"
						max="20"
						step="0.5"
						bind:value={specularSaturation}
						class="border-foreground/10 bg-foreground/5 text-foreground/60 w-14 rounded border px-1.5 py-0.5 text-right font-mono outline-none"
					/>
				</label>

				<!-- specular angle -->
				<label class="flex items-center gap-2">
					<span class="text-foreground/60 w-28 shrink-0">specular angle</span>
					<input
						type="range"
						min="0"
						max="360"
						step="5"
						bind:value={specularAngle}
						class="flex-1"
					/>
					<input
						type="number"
						min="0"
						max="360"
						step="5"
						bind:value={specularAngle}
						class="border-foreground/10 bg-foreground/5 text-foreground/60 w-14 rounded border px-1.5 py-0.5 text-right font-mono outline-none"
					/>
				</label>

				<!-- chromatic aberration -->
				<label class="flex items-center gap-2">
					<span class="text-foreground/60 w-28 shrink-0">chromatic</span>
					<input
						type="range"
						min="0"
						max="0.3"
						step="0.01"
						bind:value={chromaticAberration}
						class="flex-1"
					/>
					<input
						type="number"
						min="0"
						max="0.3"
						step="0.01"
						bind:value={chromaticAberration}
						class="border-foreground/10 bg-foreground/5 text-foreground/60 w-14 rounded border px-1.5 py-0.5 text-right font-mono outline-none"
					/>
				</label>

				<!-- glass tint -->
				<label class="flex items-center gap-2">
					<span class="text-foreground/60 w-28 shrink-0">glass tint</span>
					<input
						type="range"
						min="0"
						max="0.15"
						step="0.005"
						bind:value={glassTint}
						class="flex-1"
					/>
					<input
						type="number"
						min="0"
						max="0.15"
						step="0.005"
						bind:value={glassTint}
						class="border-foreground/10 bg-foreground/5 text-foreground/60 w-14 rounded border px-1.5 py-0.5 text-right font-mono outline-none"
					/>
				</label>
			</div>
		</div>
	</section>
</div>
