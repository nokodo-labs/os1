<script lang="ts">
	import Check from '$lib/components/icons/Check.svelte'
	import Clipboard from '$lib/components/icons/Clipboard.svelte'

	interface Props {
		content: string | (() => string)
		class?: string
	}

	let { content, class: className = '' }: Props = $props()

	let copied = $state(false)
	let timeoutId: number | undefined

	async function handleCopy() {
		try {
			const text = typeof content === 'function' ? content() : content

			if (navigator.clipboard && window.isSecureContext) {
				// use Clipboard API
				await navigator.clipboard.writeText(text)
			} else {
				// fallback method
				const textArea = document.createElement('textarea')
				textArea.value = text
				// make the textarea out of viewport
				textArea.style.position = 'fixed'
				textArea.style.top = '0'
				textArea.style.left = '0'
				document.body.appendChild(textArea)
				textArea.select()
				document.execCommand('copy')
				textArea.remove()
			}

			copied = true
			if (timeoutId) clearTimeout(timeoutId)
			timeoutId = window.setTimeout(() => {
				copied = false
			}, 1383)
		} catch (e) {
			console.error('failed to copy to clipboard', e)
		}
	}
</script>

<button
	type="button"
	class="flex h-6 w-6 cursor-pointer items-center justify-center transition-all duration-150 hover:scale-[1.05] active:scale-[0.97] {copied
		? 'text-green-400'
		: 'text-white/80 hover:text-white'} {className}"
	onclick={handleCopy}
	aria-label={copied ? 'copied' : 'copy message'}
>
	{#if copied}
		<Check class="h-4 w-4" strokeWidth="2.5" />
	{:else}
		<Clipboard class="h-4 w-4" strokeWidth="2" />
	{/if}
</button>
