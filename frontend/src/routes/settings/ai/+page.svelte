<script lang="ts">
	import Brain from '$lib/components/icons/Brain.svelte'
	import Knobs from '$lib/components/icons/Knobs.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import { ActionButton, Switch } from '$lib/components/primitives'
	import { aiFields } from '$lib/components/settings/fields/ai'
	import SettingsField from '$lib/components/settings/SettingsField.svelte'
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
		<SettingsField field={aiFields.useAccountBio}>
			{#snippet control(labelId)}
				<Switch
					size="md"
					checked={useAccountBio}
					onchange={setUseAccountBio}
					ariaLabelledbyId={labelId}
				/>
			{/snippet}

			{#if !useAccountBio}
				<div
					class="border-foreground/15 mt-5 border-t pt-5"
					transition:slide={{ duration: 200 }}
				>
					<SettingsField field={aiFields.aiBio} surface="plain" size="sm">
						<textarea
							class="border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 mt-3 w-full resize-none rounded-xl border px-4 py-3 text-sm transition-colors outline-none"
							rows="4"
							placeholder="e.g., i'm a software engineer interested in AI and design..."
							value={aiBio}
							oninput={(e) => setAiBio(e.currentTarget.value)}
						></textarea>
					</SettingsField>
				</div>
			{/if}
		</SettingsField>

		<!-- memories -->
		<SettingsField field={aiFields.memories}>
			{#snippet leading()}
				<Brain class="text-foreground/60 h-5 w-5" />
			{/snippet}

			<div class="mt-4 space-y-3">
				<SettingsField field={aiFields.enableMemories} surface="plain" size="row">
					{#snippet control(labelId)}
						<Switch
							size="md"
							checked={memoriesEnabled}
							onchange={setMemoriesEnabled}
							ariaLabelledbyId={labelId}
						/>
					{/snippet}
				</SettingsField>

				{#if memoriesEnabled}
					<div transition:slide={{ duration: 200 }}>
						<SettingsField field={aiFields.chatRecall} surface="plain" size="row">
							{#snippet control(labelId)}
								<Switch
									size="md"
									checked={chatRecall}
									onchange={setChatRecall}
									ariaLabelledbyId={labelId}
								/>
							{/snippet}
						</SettingsField>
					</div>

					<div
						class="border-foreground/15 mt-3 border-t pt-3"
						transition:slide={{ duration: 200 }}
					>
						<ActionButton
							variant="secondary"
							class="w-full"
							onclick={() => modals.open('memories')}
						>
							<Knobs class="h-4 w-4" />
							manage memories
						</ActionButton>
					</div>
				{/if}
			</div>
		</SettingsField>

		<!-- custom instructions -->
		<SettingsField field={aiFields.customInstructions}>
			<textarea
				class="border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 mt-3 w-full resize-none rounded-xl border px-4 py-3 text-sm transition-colors outline-none"
				rows="4"
				placeholder="e.g., always respond in a casual tone, prefer code examples in TypeScript..."
				value={customInstructions}
				oninput={(e) => setCustomInstructions(e.currentTarget.value)}
			></textarea>
		</SettingsField>

		<!-- AI personality -->
		<SettingsField field={aiFields.personality}>
			<textarea
				class="border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 mt-3 w-full resize-none rounded-xl border px-4 py-3 text-sm transition-colors outline-none"
				rows="3"
				placeholder="e.g., friendly and concise, like talking to a knowledgeable colleague..."
				value={personality}
				oninput={(e) => setPersonality(e.currentTarget.value)}
			></textarea>
		</SettingsField>
	</div>
</SettingsSectionLayout>
