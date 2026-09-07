<script lang="ts">
	import {
		EntranceController,
		FLIP_MS,
		inputBoxMorphSource,
		type EntranceMode,
	} from '$lib/animations/entrance.svelte'
	import AssistantChatMessage from '$lib/components/chat/AssistantChatMessage.svelte'
	import ChatGptLoadingIndicator from '$lib/components/chat/ChatGptLoadingIndicator.svelte'
	import ChatInput from '$lib/components/chat/ChatInput.svelte'
	import UserChatMessage from '$lib/components/chat/UserChatMessage.svelte'
	import Clock from '$lib/components/icons/Clock.svelte'
	import { tryUseDebugUi } from '$lib/contexts/debugUiContext.svelte'
	import { tick } from 'svelte'

	// mock chat harness (no backend): step the send -> persist -> stream lifecycle
	// by hand to inspect the outgoing-message animation frame by frame.

	type SendAnimationMode = 'morph-flip' | 'flyup' | 'none'

	const MODES: { key: SendAnimationMode; label: string }[] = [
		{ key: 'morph-flip', label: 'morph FLIP' },
		{ key: 'flyup', label: 'flyup' },
		{ key: 'none', label: 'none' },
	]
	const entranceMode = $derived.by((): EntranceMode => {
		if (reducedMotion) return 'none'
		if (animationMode === 'morph-flip') return 'morph'
		if (animationMode === 'flyup') return 'flyup'
		return 'none'
	})
	const entrance = new EntranceController(
		() => entranceMode,
		() => durationScale
	)
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

	// harness-local mode (seeded from the real setting, never written back).
	let animationMode = $state<SendAnimationMode>(
		debugUi?.sendAnimationMode === 'flyup'
			? 'flyup'
			: debugUi?.sendAnimationMode === 'none'
				? 'none'
				: 'morph-flip'
	)
	let autoPersist = $state(false)
	// fraction of the flight at which auto-persist fires, so the placeholder
	// push-up + retarget happen mid-flight (as the backend persist does in prod).
	let autoPersistAt = $state(35)
	let autoPersistTimer: number | null = null
	// slow-mo knob: 1 = production speed, higher stretches the whole entrance.
	let durationScale = $state(1)
	let controlsOpen = $state(true)
	let inputValue = $state('')

	let history = $state<HistoryEntry[]>([])

	// active turn state
	let sentText = $state('')
	let optimisticVisible = $state(false)
	let userPersisted = $state(false)
	let placeholderVisible = $state(false)
	let streamingText = $state('')
	let chunkIndex = $state(0)

	// flyup animates the real bubble (clock added only once settled); FLIP flies a
	// ghost (clock rides it, removed reactively on persist).
	let entranceSettled = $state(false)
	// persisted, tracked separately from the optimistic -> real swap (flyup defers
	// that), so the clock feedback is immediate even when the swap is held back.
	let persistRequested = $state(false)

	// any entrance animation is running (only flyup defers the persist swap).
	let morphInFlight = $state(false)
	let optimisticMsgEl = $state<HTMLElement | null>(null)
	let inputBoxEl = $state<HTMLElement | null>(null)
	// scroll container + swap-stable user-bubble wrapper, so the tracking morph can
	// re-measure the landing bubble as the thread scrolls under it.
	let scrollEl = $state<HTMLElement | null>(null)
	let userBubbleEl = $state<HTMLElement | null>(null)
	// seed-message count for the inject button (fills + scrolls the thread).
	let injectCount = $state(40)
	let persistDeferred = false

	// only flyup (animates the real bubble) defers the swap; FLIP uses a ghost.
	const deferSwapWhileAnimating = $derived(animationMode === 'flyup')
	// clock on the settled bubble; while a FLIP ghost flies, the clock rides it.
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

	function scrollToBottom(): void {
		if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight
	}

	function clearAutoPersist(): void {
		if (autoPersistTimer !== null) {
			clearTimeout(autoPersistTimer)
			autoPersistTimer = null
		}
	}

	function injectMessages(n: number): void {
		const base = history.length
		const add: HistoryEntry[] = []
		for (let i = 0; i < n; i++) {
			const role: 'user' | 'assistant' = i % 2 === 0 ? 'user' : 'assistant'
			add.push({
				id: `seed-${Date.now()}-${base + i}`,
				role,
				text:
					role === 'user'
						? `seed user message #${base + i + 1}`
						: `seed assistant reply #${base + i + 1}, with a little more text so it spans a couple of lines and takes up vertical space in the transcript.`,
			})
		}
		history = [...history, ...add]
		void tick().then(scrollToBottom)
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
		clearAutoPersist()

		if (reducedMotion || animationMode === 'none') {
			optimisticVisible = true
			markEntranceSettled()
			if (autoPersist) {
				await nextFrame()
				await persistUser()
			}
		} else if (animationMode === 'morph-flip') {
			optimisticVisible = true
			// resolve the landing bubble off the swap-stable wrapper so the morph
			// keeps tracking it across the optimistic -> persisted swap.
			const target = () =>
				userBubbleEl?.querySelector('.bubble-content') as HTMLElement | null
			const source = inputBoxMorphSource(inputBoxEl)
			// timer (not gated on the await below) so auto-persist fires mid-flight
			// like the backend, pushing the bubble up to retarget.
			if (autoPersist) {
				const delay = (autoPersistAt / 100) * FLIP_MS * durationScale
				autoPersistTimer = window.setTimeout(() => void persistUser(), delay)
			}
			// scroll to bottom before measuring so the target sits in its final slot.
			await entrance.morphTo(source, target, trimmed, scrollToBottom)
			markEntranceSettled()
		} else {
			// flyup
			morphInFlight = true
			optimisticVisible = true
			const target = () =>
				optimisticMsgEl?.querySelector('.bubble-content') as HTMLElement | null
			await entrance.animateFrom(null, target, trimmed)
			markEntranceSettled()
			if (autoPersist) {
				await nextFrame()
				await persistUser()
			}
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
		// flyup swaps the real bubble, so defer until it settles (mid-flight swap
		// aborts the animation); FLIP uses a ghost and swaps immediately.
		if (morphInFlight && deferSwapWhileAnimating) {
			persistDeferred = true
			return
		}
		applyPersist()
		await tick()
		// emulate autoscroll-on-placeholder: the inserted assistant placeholder
		// pushes the user bubble up, which the live-tracking morph then follows.
		scrollToBottom()
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
		clearAutoPersist()
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

		<div>
			<label class="flex items-center justify-between gap-3">
				<span class="text-foreground/75 text-sm">auto-persist (mid-flight)</span>
				<input type="checkbox" bind:checked={autoPersist} />
			</label>
			{#if autoPersist}
				<div class="mt-2 flex items-center justify-between gap-2 text-xs">
					<span class="text-foreground/50">persist at</span>
					<span class="text-foreground/70 font-mono">{autoPersistAt}% of flight</span>
				</div>
				<input
					type="range"
					min="5"
					max="90"
					step="5"
					bind:value={autoPersistAt}
					class="accent-foreground w-full"
				/>
			{/if}
		</div>

		<div>
			<div
				class="text-foreground/50 mb-2 flex items-center justify-between gap-2 text-xs font-semibold uppercase"
			>
				<span>animation duration</span>
				<span class="text-foreground/70 font-mono normal-case">
					{durationScale}x · {Math.round(FLIP_MS * durationScale)}ms
				</span>
			</div>
			<input
				type="range"
				min="1"
				max="50"
				step="1"
				bind:value={durationScale}
				class="accent-foreground w-full"
			/>
		</div>

		<div>
			<div class="text-foreground/50 mb-2 text-xs font-semibold uppercase">
				seed transcript
			</div>
			<div class="flex items-center gap-2">
				<input
					type="number"
					min="1"
					max="500"
					bind:value={injectCount}
					class="border-foreground/15 bg-foreground/5 text-foreground w-20 rounded-lg border px-2 py-1 text-sm"
				/>
				<button
					type="button"
					onclick={() => injectMessages(injectCount)}
					class="rounded-xl bg-foreground/10 text-foreground/85 hover:bg-foreground/15 flex-1 px-3 py-2 text-sm transition"
				>
					inject messages
				</button>
			</div>
			<p class="text-foreground/45 mt-1 text-xs leading-relaxed">
				pre-fills the thread + scrolls to bottom, so sending pushes the bubble up and (on
				persist) retargets the morph.
			</p>
		</div>

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
		<div class="flex-1 overflow-y-auto px-4 py-6" bind:this={scrollEl}>
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
					<!-- landing bubble hidden while the ghost flies; the outer wrapper is
					     swap-stable (optimistic -> persisted) so the morph keeps tracking it. -->
					<div style:opacity={entrance.inFlight ? '0' : '1'} bind:this={userBubbleEl}>
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
		<!-- entrance morph ghost: morphs the input box into the bubble; carries the
		     sending clock until the message persists. -->
		<div
			bind:this={entrance.ghostEl}
			class="text-foreground pointer-events-none fixed z-50 block rounded-3xl px-3 py-2"
			aria-hidden="true"
			style="left: {entrance.ghost.left}px; top: {entrance.ghost.top}px; width: {entrance
				.ghost.width}px; height: {entrance.ghost
				.height}px; background-color: var(--accent-primary); box-shadow: 0 4px 16px var(--accent-border);"
		>
			{#if !persistRequested}
				<span
					class="text-foreground/55 pointer-events-none absolute top-1/2 -left-6 flex size-4 -translate-y-1/2 items-center justify-center"
				>
					<span class="ghost-clock-tick flex size-4 items-center justify-center">
						<Clock class="h-4 w-4" strokeWidth="2" />
					</span>
				</span>
			{/if}
			<span class="leading-relaxed whitespace-pre-wrap wrap-break-word"
				>{entrance.ghost.text}</span
			>
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
