<script lang="ts">
	import Brain from '$lib/components/icons/Brain.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import { Switch } from '$lib/components/primitives'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import { debounce } from '$lib/utils'
	import { slide } from 'svelte/transition'

	// reactive getters
	const useAccountBio = $derived(preferences.data.ai.useAccountBio ?? false)
	const aiBio = $derived(preferences.data.ai.bio ?? '')
	const memoriesEnabled = $derived(preferences.data.ai.memoriesEnabled ?? true)
	const chatRecall = $derived(preferences.data.ai.chatRecall ?? true)
	const customInstructions = $derived(preferences.data.ai.customInstructions ?? '')
	const personality = $derived(preferences.data.ai.personality ?? '')

	// debounced text updates
	const saveAiBio = debounce(
		(value: string) => void preferences.update('ai', { bio: value || null }),
		600
	)
	const saveCustomInstructions = debounce(
		(value: string) => void preferences.update('ai', { customInstructions: value || null }),
		600
	)
	const savePersonality = debounce(
		(value: string) => void preferences.update('ai', { personality: value || null }),
		600
	)

	function setUseAccountBio(enabled: boolean): void {
		void preferences.update('ai', { useAccountBio: enabled })
	}

	function setAiBio(value: string): void {
		saveAiBio(value)
	}

	function setMemoriesEnabled(enabled: boolean): void {
		void preferences.update('ai', { memoriesEnabled: enabled })
	}

	function setChatRecall(enabled: boolean): void {
		void preferences.update('ai', { chatRecall: enabled })
	}

	function setCustomInstructions(value: string): void {
		saveCustomInstructions(value)
	}

	function setPersonality(value: string): void {
		savePersonality(value)
	}
</script>

<SettingsSectionLayout
	icon={Sparkles}
	label="AI"
	description="customize AI behavior, personality, and memory"
>
	<div class="space-y-4">
		<!-- AI bio -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="flex items-center justify-between">
				<div>
					<div class="text-sm font-semibold text-foreground">use account bio</div>
					<div class="mt-1 text-sm text-foreground/50">
						use your account bio as context for AI conversations instead of a separate
						AI bio.
					</div>
				</div>
				<Switch size="md" checked={useAccountBio} onchange={setUseAccountBio} />
			</div>

			{#if !useAccountBio}
				<div
					class="mt-5 border-t border-foreground/15 pt-5"
					transition:slide={{ duration: 200 }}
				>
					<div class="text-sm font-semibold text-foreground">AI bio</div>
					<div class="mt-1 text-sm text-foreground/50">
						tell the AI about yourself - your interests, work, and preferences. this
						helps personalize responses.
					</div>
					<textarea
						class="mt-3 w-full resize-none rounded-xl border border-foreground/10 bg-foreground/5 px-4 py-3 text-sm text-foreground/90 placeholder:text-foreground/40 transition-colors outline-none focus:border-foreground/20 focus:bg-foreground/8"
						rows="4"
						placeholder="e.g., i'm a software engineer interested in AI and design..."
						value={aiBio}
						oninput={(e) => setAiBio(e.currentTarget.value)}
					></textarea>
				</div>
			{/if}
		</div>

		<!-- memories -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="flex items-center gap-3 pb-1">
				<Brain class="h-5 w-5 text-foreground/60" />
				<div class="text-sm font-semibold text-foreground">memories</div>
			</div>
			<div class="mt-1 text-sm text-foreground/50">
				the AI remembers things you tell it across conversations to provide more relevant
				responses.
			</div>

			<div class="mt-4 space-y-3">
				<div class="flex items-center justify-between">
					<span class="text-sm text-foreground/70">enable memories</span>
					<Switch size="md" checked={memoriesEnabled} onchange={setMemoriesEnabled} />
				</div>

				{#if memoriesEnabled}
					<div transition:slide={{ duration: 200 }}>
						<div class="flex items-center justify-between">
							<span class="text-sm text-foreground/70">chat recall</span>
							<Switch size="md" checked={chatRecall} onchange={setChatRecall} />
						</div>
						<div class="mt-1 pl-0 text-xs text-foreground/40">
							allow the AI to reference previous conversations for context.
						</div>
					</div>

					<div
						class="mt-3 border-t border-foreground/15 pt-3"
						transition:slide={{ duration: 200 }}
					>
						<div class="flex items-center justify-between">
							<div class="text-sm font-medium text-foreground/70">manage memories</div>
							<button
								type="button"
								class="rounded-pill flex items-center gap-1.5 border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-xs text-foreground/60 transition-all hover:border-foreground/20 hover:bg-foreground/10 hover:text-foreground/80"
								onclick={() => modals.open('memories')}
							>
								<Brain class="h-3.5 w-3.5" />
								manage
							</button>
						</div>
					</div>
				{/if}
			</div>
		</div>

		<!-- custom instructions -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-foreground">custom instructions</div>
			<div class="mt-1 text-sm text-foreground/50">
				provide specific instructions the AI should always follow. these apply to every
				conversation.
			</div>
			<textarea
				class="mt-3 w-full resize-none rounded-xl border border-foreground/10 bg-foreground/5 px-4 py-3 text-sm text-foreground/90 placeholder:text-foreground/40 transition-colors outline-none focus:border-foreground/20 focus:bg-foreground/8"
				rows="4"
				placeholder="e.g., always respond in a casual tone, prefer code examples in TypeScript..."
				value={customInstructions}
				oninput={(e) => setCustomInstructions(e.currentTarget.value)}
			></textarea>
		</div>

		<!-- AI personality -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-foreground">personality</div>
			<div class="mt-1 text-sm text-foreground/50">
				describe how you'd like the AI to communicate - its tone, style, and character.
			</div>
			<textarea
				class="mt-3 w-full resize-none rounded-xl border border-foreground/10 bg-foreground/5 px-4 py-3 text-sm text-foreground/90 placeholder:text-foreground/40 transition-colors outline-none focus:border-foreground/20 focus:bg-foreground/8"
				rows="3"
				placeholder="e.g., friendly and concise, like talking to a knowledgeable colleague..."
				value={personality}
				oninput={(e) => setPersonality(e.currentTarget.value)}
			></textarea>
		</div>
	</div>
</SettingsSectionLayout>
