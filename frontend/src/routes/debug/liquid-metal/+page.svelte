<script lang="ts">
	import { Slider } from '$lib/components/primitives'
	import LiquidMetalFilter from '$lib/liquid-metal/svg/LiquidMetalFilter.svelte'

	const BG_IMAGE = 'https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?w=1200&q=80'

	let bezelWidth = $state(18)
	let thickness = $state(16)
	let refractionStrength = $state(1.25)
	let mirrorDepth = $state(24)
	let specularOpacity = $state(0.85)
	let specularAngle = $state(320)
	let cornerRadius = $state(22)

	const pillFilterId = 'lm-svg-pill'
	const cardFilterId = 'lm-svg-card'
	const chipFilterId = 'lm-svg-chip'

	const pillW = 420
	const pillH = 54
	const cardW = 420
	const cardH = 160
	const chipW = 140
	const chipH = 44
	const pillRadius = $derived(Math.min(pillW, pillH) / 2)
</script>

<svelte:head>
	<title>liquid metal svg lab</title>
</svelte:head>

<LiquidMetalFilter
	filterId={pillFilterId}
	width={pillW}
	height={pillH}
	cornerRadius={pillRadius}
	{bezelWidth}
	{thickness}
	{refractionStrength}
	{mirrorDepth}
	{specularOpacity}
	{specularAngle}
/>

<LiquidMetalFilter
	filterId={cardFilterId}
	width={cardW}
	height={cardH}
	{cornerRadius}
	{bezelWidth}
	{thickness}
	{refractionStrength}
	{mirrorDepth}
	{specularOpacity}
	{specularAngle}
/>

<LiquidMetalFilter
	filterId={chipFilterId}
	width={chipW}
	height={chipH}
	{cornerRadius}
	{bezelWidth}
	{thickness}
	{refractionStrength}
	{mirrorDepth}
	{specularOpacity}
	{specularAngle}
/>

<div class="flex h-dvh w-full flex-col overflow-auto lg:flex-row">
	<section
		class="border-foreground/10 relative min-h-80 flex-1 overflow-hidden border-b lg:border-r lg:border-b-0"
	>
		<img
			src={BG_IMAGE}
			alt="background for liquid metal demo"
			class="absolute inset-0 h-full w-full object-cover"
			draggable="false"
		/>

		<div class="absolute top-3 left-4 z-30">
			<div
				class="text-foreground/80 rounded-full bg-black/55 px-3 py-1.5 text-xs font-medium"
			>
				liquid metal svg elements
			</div>
		</div>

		<div class="relative z-10 flex h-full w-full flex-col gap-4 p-6 pt-14">
			<div
				class="liquid-metal text-foreground/85 flex items-center px-5 text-sm"
				style="width: {pillW}px; height: {pillH}px; border-radius: {pillRadius}px; filter: url(#{pillFilterId});"
			>
				metal nav pill
			</div>

			<div
				class="liquid-metal text-foreground/82 px-5 py-4 text-sm"
				style="width: {cardW}px; height: {cardH}px; border-radius: {cornerRadius}px; filter: url(#{cardFilterId});"
			>
				<div class="text-foreground/92 font-semibold">metal card</div>
				<div class="text-foreground/65 mt-2">
					edge reflections only, opaque mirror surface
				</div>
				<div class="mt-4 flex gap-2">
					<div
						class="liquid-metal text-foreground/90 grid place-items-center text-xs"
						style="width: {chipW}px; height: {chipH}px; border-radius: {cornerRadius}px; filter: url(#{chipFilterId});"
					>
						chip one
					</div>
					<div
						class="liquid-metal text-foreground/90 grid place-items-center text-xs"
						style="width: {chipW}px; height: {chipH}px; border-radius: {cornerRadius}px; filter: url(#{chipFilterId});"
					>
						chip two
					</div>
				</div>
			</div>
		</div>
	</section>

	<section class="min-h-80 flex-1 bg-black/35 p-6">
		<div class="text-foreground/60 text-xs font-semibold tracking-wider uppercase">
			controls
		</div>
		<div class="mt-4 grid gap-5">
			<div>
				<div class="text-foreground/65 mb-2 text-xs">bezel width: {bezelWidth}px</div>
				<Slider bind:value={bezelWidth} min={8} max={36} step={1} />
			</div>
			<div>
				<div class="text-foreground/65 mb-2 text-xs">thickness: {thickness}px</div>
				<Slider bind:value={thickness} min={8} max={40} step={1} />
			</div>
			<div>
				<div class="text-foreground/65 mb-2 text-xs">
					reflection warp: {refractionStrength.toFixed(2)}
				</div>
				<Slider bind:value={refractionStrength} min={0.6} max={2.2} step={0.01} />
			</div>
			<div>
				<div class="text-foreground/65 mb-2 text-xs">mirror depth: {mirrorDepth}px</div>
				<Slider bind:value={mirrorDepth} min={8} max={42} step={1} />
			</div>
			<div>
				<div class="text-foreground/65 mb-2 text-xs">
					specular opacity: {specularOpacity.toFixed(2)}
				</div>
				<Slider bind:value={specularOpacity} min={0.2} max={1} step={0.01} />
			</div>
			<div>
				<div class="text-foreground/65 mb-2 text-xs">
					specular angle: {specularAngle}deg
				</div>
				<Slider bind:value={specularAngle} min={0} max={360} step={1} />
			</div>
		</div>
	</section>
</div>
