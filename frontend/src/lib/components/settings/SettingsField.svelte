<script lang="ts">
	import type { Snippet } from 'svelte'
	import { settingsFieldAnchor } from './fieldFocus'
	import type { SettingsFieldDef } from './fields/types'

	/**
	 * one settings field, rendered from its declaration.
	 *
	 * the label and description come from the shared field module, so the search
	 * index and the page always show the same words. the field registers itself
	 * as a reveal anchor, which is how a search result scrolls here.
	 */
	interface Props {
		field: SettingsFieldDef
		/** `card` draws the glass container; `plain` is a row inside one. */
		surface?: 'card' | 'plain'
		/** `md` titles a card, `sm` a block nested in one, `row` a single control. */
		size?: 'md' | 'sm' | 'row'
		/** `wrap` lets the control drop below the label on narrow screens. */
		controlLayout?: 'inline' | 'wrap'
		/** runtime wording for a description that depends on state. */
		description?: string
		class?: string
		leading?: Snippet
		control?: Snippet<[string]>
		children?: Snippet
	}

	let {
		field,
		surface = 'card',
		size = 'md',
		controlLayout = 'inline',
		description,
		class: className = '',
		leading,
		control,
		children,
	}: Props = $props()

	const labelId = $derived(`settings-field-${field.id}`)
	const text = $derived(description ?? field.description)

	const surfaceClass = $derived(
		surface === 'card' ? 'rounded-container liquid-glass liquid-glass--frosted p-5' : ''
	)
	const headerClass = $derived(
		controlLayout === 'wrap'
			? 'flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between'
			: 'flex items-start justify-between gap-4'
	)
	const labelClass = $derived(
		size === 'md'
			? 'text-foreground/85 text-base font-[650]'
			: size === 'sm'
				? 'text-foreground/85 text-sm font-semibold'
				: 'text-foreground/70 text-sm'
	)
	const textClass = $derived(
		size === 'row' ? 'text-foreground/50 mt-0.5 text-xs' : 'text-foreground/55 mt-1 text-sm'
	)
</script>

<div class="{surfaceClass} {className}" {@attach settingsFieldAnchor(field.id)}>
	<div class={headerClass}>
		<div class="flex min-w-0 items-start gap-3">
			{#if leading}
				<div class="shrink-0">{@render leading()}</div>
			{/if}
			<div class="min-w-0">
				<div id={labelId} class={labelClass}>{field.label}</div>
				{#if text}
					<div class={textClass}>{text}</div>
				{/if}
			</div>
		</div>
		{#if control}
			{@render control(labelId)}
		{/if}
	</div>
	{@render children?.()}
</div>
