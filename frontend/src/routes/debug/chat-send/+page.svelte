<script lang="ts">
	import { EntranceController, type EntranceMode } from '$lib/animations/entrance.svelte'
	import AssistantChatMessage from '$lib/components/chat/AssistantChatMessage.svelte'
	import ChatGptLoadingIndicator from '$lib/components/chat/ChatGptLoadingIndicator.svelte'
	import ChatInput from '$lib/components/chat/ChatInput.svelte'
	import UserChatMessage from '$lib/components/chat/UserChatMessage.svelte'
	import Clock from '$lib/components/icons/Clock.svelte'
	import { tryUseDebugUi } from '$lib/contexts/debugUiContext.svelte'
	import { tick } from 'svelte'

	// mock chat harness: step through the send -> persist -> stream lifecycle by
	// hand, with NO backend, so the outgoing-message animation can be inspected
	// frame by frame and tested against instant vs delayed persistence.

	type SendAnimationMode = 'morph-flip' | 'flyup' | 'none'

	const MODES: { key: SendAnimationMode; label: string }[] = [
		{ key: 'morph-flip', label: 'morph FLIP' },
		{ key: 'flyup', label: 'flyup' },
		{ key: 'none', label: 'none' },
	]
	// entrance controller delegates to FLIP morph or flyup WAAPI based on the
	// harness's locally-selected animationMode.
	const entranceMode = $derived.by((): EntranceMode => {
		if (reducedMotion) return 'none'
		if (animationMode === 'morph-flip') return 'morph'
		if (animationMode === 'flyup') return 'flyup'
		return 'none'
	})
	const entrance = new EntranceController(() => entranceMode)
	const SAMPLE_PROMPT = 'walk me through the send animation lifecycle, step by step'
	const SAMPLE_CHUNKS = [
		'sure thing. ',
		'first the user bubble morphs out of the input, ',
		'then it settles into the thread, ',
		'and only after it persists ',
		'does the assistant placeholder appear. ',
		'finally the response streams in token by token.',
	]

	interface HistoryEntry {
		id: string
		role: 'user' | 'assistant'
		text: string
	}

	const debugUi = tryUseDebugUi()
	const reducedMotion =
		typeof window !== 'undefined' &&
		typeof window.matchMedia === 'function' &&
		window.matchMedia('(prefers-reduced-motion: reduce)').matches

	// controls. the harness owns its mode locally: it includes morph-flip, which
	// the real-page debug setting cannot represent yet. the initial value mirrors
	// the real setting (morph -> morph-flip) but changes here do NOT write back.
	let animationMode = $state<SendAnimationMode>(
		debugUi?.sendAnimationMode === 'flyup'
			? 'flyup'
			: debugUi?.sendAnimationMode === 'none'
				? 'none'
				: 'morph-flip'
	)
	let autoPersist = $state(false)
	let controlsOpen = $state(true)
	let inputValue = $state('')

	// completed turns
	let history = $state<HistoryEntry[]>([])

	// active turn state machine
	let sentText = $state('')
	let optimisticVisible = $state(false)
	let userPersisted = $state(false)
	let placeholderVisible = $state(false)
	let streamingText = $state('')
	let chunkIndex = $state(0)

	// entrance animation lifecycle.
	// - flyup animates the real bubble, so the clock can only be added once the
	//   animation settles (mutating the bubble mid-flight would abort it).
	// - FLIP animates a standalone ghost, so the clock rides the ghost immediately
	//   and is removed reactively the instant the message persists.
	let entranceSettled = $state(false)
	// "the message has been persisted" - tracked separately from the optimistic ->
	// real swap, which flyup defers until its animation finishes. drives the clock
	// so the feedback is immediate even when the swap itself is held back.
	let persistRequested = $state(false)

	// outgoing-message morph orchestration. morphInFlight marks any entrance
	// animation as running; the persist deferral only applies to flyup, which
	// animates the real bubble.
	let morphInFlight = $state(false)
	let optimisticMsgEl = $state<HTMLElement | null>(null)
	let inputBoxEl = $state<HTMLElement | null>(null)
	// when a persist arrives mid-animation in flyup, hold the swap until it
	// finishes - swapping the element mid-flight aborts it.
	let persistDeferred = false

	// flyup animates the real bubble, so it must defer the optimistic -> real
	// swap during the entrance animation; FLIP animates a ghost instead, so it
	// never defers.
	const deferSwapWhileAnimating = $derived(animationMode === 'flyup')
	// clock visibility on the settled bubble. while a FLIP ghost is flying the clock
	// rides the ghost instead (shown there while !persistRequested).
	const bubbleClockVisible = $derived.by(() => {
		if (persistRequested) return false
		if (animationMode === 'morph-flip') return !entrance.inFlight
		if (animationMode === 'none') return true
		return entranceSettled
	})

	const phase = $derived(
		streamingText
			? 'streaming'
			: placeholderVisible
				? 'awaiting response'
				: optimisticVisible
					? 'sent (optimistic)'
					: 'idle'
	)

	const isActive = $derived(optimisticVisible || userPersisted)
	const chunksRemaining = $derived(chunkIndex < SAMPLE_CHUNKS.length)

	function selectMode(mode: SendAnimationMode): void {
		animationMode = mode
	}

	function nextFrame(): Promise<void> {
		return new Promise((resolve) => {
			requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
		})
	}

	function markEntranceSettled(): void {
		morphInFlight = false
		entranceSettled = true
		flushDeferredPersist()
	}

	async function doSend(text: string): Promise<void> {
		const trimmed = text.trim()
		if (!trimmed || isActive) return
		sentText = trimmed
		inputValue = ''
		entranceSettled = false
		persistRequested = false
		morphInFlight = false

		if (reducedMotion || animationMode === 'none') {
			optimisticVisible = true
			markEntranceSettled()
		} else if (animationMode === 'morph-flip') {
			optimisticVisible = true
			const target = () =>
				optimisticMsgEl?.querySelector('.bubble-content') as HTMLElement | null
			await entrance.animateFrom(inputBoxEl, target, trimmed)
			markEntranceSettled()
		} else {
			// flyup
			morphInFlight = true
			optimisticVisible = true
			const target = () =>
				optimisticMsgEl?.querySelector('.bubble-content') as HTMLElement | null
			await entrance.animateFrom(null, target, trimmed)
			markEntranceSettled()
		}

		if (autoPersist) {
			// "instant" persistence still lands after at least one painted frame;
			// the swap itself is deferred until the entrance animation finishes.
			await nextFrame()
			await persistUser()
		}
	}

	function applyPersist(): void {
		optimisticVisible = false
		userPersisted = true
		// in production the run is already active, so the assistant "thinking"
		// placeholder appears the instant the user message persists.
		placeholderVisible = true
	}

	function flushDeferredPersist(): void {
		if (!persistDeferred) return
		persistDeferred = false
		applyPersist()
	}

	async function persistUser(): Promise<void> {
		if (!optimisticVisible || userPersisted) return
		// feedback is immediate: the clock reacts to persistRequested even when the
		// actual swap is deferred.
		persistRequested = true
		// flyup animates the real bubble, so defer the swap until the entrance
		// animation settles (swapping mid-flight aborts it). FLIP animates a ghost,
		// so it swaps immediately - the hidden landing bubble simply updates.
		if (morphInFlight && deferSwapWhileAnimating) {
			persistDeferred = true
			return
		}
		applyPersist()
		await tick()
	}

	function pushChunk(): void {
		if (!userPersisted) return
		if (!chunksRemaining) return
		placeholderVisible = false
		streamingText += SAMPLE_CHUNKS[chunkIndex]
		chunkIndex += 1
	}

	function finishTurn(): void {
		if (!userPersisted) return
		const userId = `u-${Date.now()}`
		const assistantId = `a-${Date.now()}`
		const next: HistoryEntry[] = [...history, { id: userId, role: 'user', text: sentText }]
		if (streamingText) next.push({ id: assistantId, role: 'assistant', text: streamingText })
		history = next
		resetActiveTurn()
	}

	function resetActiveTurn(): void {
		sentText = ''
		optimisticVisible = false
		userPersisted = false
		placeholderVisible = false
		streamingText = ''
		chunkIndex = 0
		persistDeferred = false
		entranceSettled = false
		persistRequested = false
		entrance.reset()
	}

	function resetAll(): void {
		resetActiveTurn()
		history = []
		inputValue = ''
		morphInFlight = false
	}
</script>

<div class="flex h-full min-h-0 w-full flex-col gap-4 p-4 lg:flex-row">
	<!-- control panel: collapsible on mobile so the chat surface stays usable -->
	<aside
		class="border-foreground/10 bg-foreground/3 flex w-full shrink-0 flex-col gap-4 overflow-y-auto rounded-2xl border p-4 lg:w-80 lg:max-h-none lg:overflow-visible {controlsOpen
			? 'max-h-[45vh]'
			: 'max-h-16'}"
	>
		<div class="flex items-center justify-between gap-2">
			<h1 class="text-foreground text-lg font-semibold">chat send harness</h1>
			<button
				type="button"
				onclick={() => (controlsOpen = !controlsOpen)}
				class="rounded-pill bg-foreground/5 text-foreground/55 hover:text-foreground px-3 py-1 text-xs lg:hidden"
			>
				{controlsOpen ? 'hide' : 'show'}
			</button>
		</div>
		<p class="text-foreground/55 -mt-2 text-xs leading-relaxed">
			mock chat with no backend. step through each phase by hand to inspect the outgoing
			message animation. in production the user message persists within milliseconds, so use
			auto-persist to reproduce that timing.
		</p>

		<div class="border-foreground/10 rounded-xl border p-3">
			<div class="text-foreground/50 text-xs font-semibold uppercase">phase</div>
			<div class="text-foreground/85 mt-1 font-mono text-sm">{phase}</div>
		</div>

		<div>
			<div class="text-foreground/50 mb-2 text-xs font-semibold uppercase">
				animation mode
			</div>
			<div class="flex flex-wrap gap-1">
				{#each MODES as mode (mode.key)}
					<button
						type="button"
						onclick={() => selectMode(mode.key)}
						class="rounded-pill px-3 py-1.5 text-xs transition-colors {animationMode ===
						mode.key
							? 'bg-foreground/15 text-foreground'
							: 'bg-foreground/5 text-foreground/60 hover:bg-foreground/10 hover:text-foreground/80'}"
					>
						{mode.label}
					</button>
				{/each}
			</div>
			{#if reducedMotion && animationMode !== 'none'}
				<p class="mt-2 text-xs text-amber-500">
					prefers-reduced-motion is on: morph and flyup are suppressed.
				</p>
			{/if}
		</div>

		<label class="flex items-center justify-between gap-3">
			<span class="text-foreground/75 text-sm">auto-persist (instant)</span>
			<input type="checkbox" bind:checked={autoPersist} />
		</label>

		<div class="border-foreground/10 border-t"></div>

		<div class="flex flex-col gap-2">
			<div class="text-foreground/50 text-xs font-semibold uppercase">steps</div>
			<button
				type="button"
				onclick={() => doSend(SAMPLE_PROMPT)}
				disabled={isActive}
				class="rounded-xl bg-foreground/10 text-foreground/85 hover:bg-foreground/15 px-3 py-2 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-40"
			>
				1 · send sample
			</button>
			<button
				type="button"
				onclick={() => persistUser()}
				disabled={!optimisticVisible}
				class="rounded-xl bg-foreground/10 text-foreground/85 hover:bg-foreground/15 px-3 py-2 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-40"
			>
				2 · persist user message (+ placeholder)
			</button>
			<button
				type="button"
				onclick={pushChunk}
				disabled={!userPersisted || !chunksRemaining}
				class="rounded-xl bg-foreground/10 text-foreground/85 hover:bg-foreground/15 px-3 py-2 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-40"
			>
				3 · push text chunk ({chunkIndex}/{SAMPLE_CHUNKS.length})
			</button>
			<button
				type="button"
				onclick={finishTurn}
				disabled={!userPersisted}
				class="rounded-xl bg-foreground/10 text-foreground/85 hover:bg-foreground/15 px-3 py-2 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-40"
			>
				4 · finish turn
			</button>
			<button
				type="button"
				onclick={resetAll}
				class="text-foreground/55 hover:text-foreground rounded-xl px-3 py-2 text-left text-sm transition"
			>
				reset all
			</button>
		</div>
	</aside>

	<!-- mock chat surface -->
	<section
		class="border-foreground/10 relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border"
	>
		<div class="flex-1 overflow-y-auto px-4 py-6">
			<div class="mx-auto flex w-full max-w-3xl flex-col gap-6">
				{#each history as entry (entry.id)}
					{#if entry.role === 'user'}
						<UserChatMessage content={entry.text} />
					{:else}
						<AssistantChatMessage content="" modelName="debug agent">
							{#snippet lead()}
								<div class="text-[0.95rem] leading-relaxed whitespace-pre-wrap">
									{entry.text}
								</div>
							{/snippet}
						</AssistantChatMessage>
					{/if}
				{/each}

				{#if optimisticVisible || userPersisted}
					<!-- the landing bubble is hidden (opacity) while the entrance ghost is in
					     flight, then revealed when it lands. -->
					<div style:opacity={entrance.inFlight ? '0' : '1'}>
						{#if optimisticVisible}
							<div bind:this={optimisticMsgEl}>
								<UserChatMessage content={sentText} sending={bubbleClockVisible} />
							</div>
						{:else}
							<UserChatMessage content={sentText} sending={bubbleClockVisible} />
						{/if}
					</div>
				{/if}

				{#if userPersisted && (placeholderVisible || streamingText)}
					<AssistantChatMessage content="" isStreaming modelName="debug agent">
						{#snippet lead()}
							{#if streamingText}
								<div class="text-[0.95rem] leading-relaxed whitespace-pre-wrap">
									{streamingText}
								</div>
							{:else}
								<div class="my-3">
									<ChatGptLoadingIndicator />
								</div>
							{/if}
						{/snippet}
					</AssistantChatMessage>
				{/if}
			</div>
		</div>

		<!-- input overlay -->
		<div class="border-foreground/10 border-t p-4">
			<div bind:this={inputBoxEl} class="relative mx-auto w-full max-w-3xl">
				<ChatInput
					bind:value={inputValue}
					onSubmit={(message) => doSend(message)}
					placeholder="type a test message"
				/>
			</div>
		</div>
	</section>

	{#if entrance.ghost}
		<!-- entrance morph ghost: flies the input box to the bubble rect (no scale,
		     so text never distorts).  carries the clock, shown immediately and removed
		     reactively the instant the message persists. -->
		<div
			bind:this={entrance.ghostEl}
			class="text-foreground pointer-events-none fixed z-50 flex items-center gap-2 overflow-hidden rounded-3xl px-3"
			aria-hidden="true"
			style="left: {entrance.ghost.left}px; top: {entrance.ghost.top}px; width: {entrance
				.ghost.width}px; height: {entrance.ghost
				.height}px; background-color: var(--accent-primary); box-shadow: 0 4px 16px var(--accent-border);"
		>
			{#if !persistRequested}
				<span class="flex size-4 shrink-0 items-center justify-center">
					<span class="ghost-clock-tick flex size-4 items-center justify-center">
						<Clock class="h-4 w-4" strokeWidth="2" />
					</span>
				</span>
			{/if}
			<span class="truncate">{entrance.ghost.text}</span>
		</div>
	{/if}
</div>

<style>
	@keyframes ghostClockTick {
		to {
			transform: rotate(360deg);
		}
	}

	.ghost-clock-tick {
		animation: ghostClockTick 1.4s steps(12) infinite;
		transform-origin: center;
	}
</style>
