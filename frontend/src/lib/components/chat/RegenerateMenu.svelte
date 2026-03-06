<script lang="ts">
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import Brain from '$lib/components/icons/Brain.svelte'
	import LineSpace from '$lib/components/icons/LineSpace.svelte'
	import LineSpaceSmaller from '$lib/components/icons/LineSpaceSmaller.svelte'
	import MenuItem from '$lib/components/primitives/MenuItem.svelte'
	import PopupMenu from '$lib/components/primitives/PopupMenu.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { tick } from 'svelte'

	interface Props {
		onRegenerate: (prompt?: string | null) => void
	}

	let { onRegenerate }: Props = $props()

	let open = $state(false)
	let anchorEl = $state<HTMLElement | null>(null)
	let inputValue = $state('')
	let inputEl = $state<HTMLInputElement | null>(null)

	function toggle() {
		open = !open
		if (open) {
			inputValue = ''
			// only auto-focus the text field on desktop
			if (!device.isMobile) {
				void tick().then(() => inputEl?.focus())
			}
		}
	}

	function close() {
		open = false
	}

	function submitCustom() {
		const val = inputValue.trim()
		if (!val) return
		onRegenerate(val)
		close()
	}

	function selectOption(prompt?: string | null) {
		onRegenerate(prompt)
		close()
	}
</script>

<div class="relative inline-flex">
	<button
		bind:this={anchorEl}
		type="button"
		class="text-foreground/80 hover:text-foreground flex h-6 w-6 cursor-pointer items-center justify-center transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97]"
		onclick={toggle}
		aria-label="regenerate options"
		aria-haspopup="menu"
		aria-expanded={open}
	>
		<ArrowPath class="h-4 w-4" strokeWidth="2" />
	</button>

	<PopupMenu {open} {anchorEl} onClose={close}>
		<div class="flex flex-col gap-0.5">
			<!-- custom instruction input -->
			<div class="flex items-center px-2.5 py-1.5">
				<input
					bind:this={inputEl}
					type="text"
					class="text-foreground/90 placeholder:text-foreground/45 w-full min-w-0 flex-1 bg-transparent text-sm outline-none"
					placeholder="suggest a change"
					bind:value={inputValue}
					onkeydown={(e) => {
						if (e.key === 'Enter') submitCustom()
					}}
				/>
				<button
					type="button"
					class="ml-2 flex shrink-0 items-center justify-center rounded-full p-1 transition {inputValue.trim()
						? 'bg-foreground text-background hover:bg-foreground/90'
						: 'bg-foreground/10 text-foreground/35'}"
					onclick={submitCustom}
					disabled={!inputValue.trim()}
					aria-label="submit"
				>
					<ArrowUp class="h-3.5 w-3.5" />
				</button>
			</div>

			<div class="border-foreground/8 mx-2 border-t"></div>

			<!-- preset options -->
			<MenuItem onclick={() => selectOption()}>
				{#snippet icon()}<ArrowPath class="h-4 w-4" />{/snippet}
				try again
			</MenuItem>

			<MenuItem onclick={() => selectOption('think long and carefully about this')}>
				{#snippet icon()}<Brain class="h-4 w-4" />{/snippet}
				think longer
			</MenuItem>

			<MenuItem onclick={() => selectOption('add more details and expand on each point')}>
				{#snippet icon()}<LineSpace class="h-4 w-4" />{/snippet}
				add details
			</MenuItem>

			<MenuItem onclick={() => selectOption('be concise, avoid unnecessary details')}>
				{#snippet icon()}<LineSpaceSmaller class="h-4 w-4" />{/snippet}
				more concise
			</MenuItem>
		</div>
	</PopupMenu>
</div>
