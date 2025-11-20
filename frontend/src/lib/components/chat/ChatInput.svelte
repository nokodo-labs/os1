<script lang="ts">
    import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
    import Plus from '$lib/components/icons/Plus.svelte'
    import Stop from '$lib/components/icons/Stop.svelte'
    import * as Tooltip from '$lib/components/ui/tooltip'

    interface ChatInputProps {
        value?: string
        placeholder?: string
        disabled?: boolean
        isGenerating?: boolean
        onSubmit?: (message: string) => void
        onStop?: () => void
    }

    let {
        value = $bindable(''),
        placeholder = 'send a message',
        disabled = false,
        isGenerating = false,
        onSubmit,
        onStop,
    }: ChatInputProps = $props()

    let textarea: HTMLTextAreaElement
    let isComposing = $state(false)

    function handleInput() {
        if (!textarea) return
        textarea.style.height = 'auto'
        textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }

    function handleKeyDown(event: KeyboardEvent) {
        // Don't submit if composing (for IME input)
        if (event.key === 'Enter' && !event.shiftKey && !isComposing) {
            event.preventDefault()
            handleSubmit()
        }
    }

    function handleSubmit() {
        if (!value.trim() || disabled || !onSubmit) return
        onSubmit(value)
        value = ''
        if (textarea) {
            textarea.style.height = 'auto'
        }
    }

    function handleCompositionStart() {
        isComposing = true
    }

    function handleCompositionEnd() {
        isComposing = false
    }

    function handleFormSubmit(event: SubmitEvent) {
        event.preventDefault()
        handleSubmit()
    }
</script>

<form class="w-full" onsubmit={handleFormSubmit}>
    <div
        class="liquid-glass relative w-full rounded-full bg-[rgba(10,12,20,0.65)] shadow-lg transition-all duration-300 ease-in-out focus-within:shadow-[0px_6px_24px_rgba(0,0,0,0.3),0_0_0_1px_rgba(255,255,255,0.15)]"
    >
        <div class="liquid-glass__highlight"></div>
        <div class="liquid-glass__content px-1 py-1">
            <div class="flex items-center gap-2 px-2.5 py-2.5">
                <div class="ml-1 flex shrink-0 items-center">
                    <Tooltip.Root>
                        <Tooltip.Trigger>
                            <button
                                type="button"
                                aria-label="Add attachment"
                                class="flex h-8 w-8 items-center justify-center rounded-full bg-transparent text-white/65 transition-all duration-200 hover:bg-white/5 hover:text-white/95 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
                                {disabled}
                            >
                                <Plus className="h-5.5 w-5.5" strokeWidth="2" />
                            </button>
                        </Tooltip.Trigger>
                        <Tooltip.Content>
                            <p>add attachment</p>
                        </Tooltip.Content>
                    </Tooltip.Root>
                </div>

                <div class="flex flex-1 items-center px-1.5">
                    <textarea
                        bind:this={textarea}
                        bind:value
                        {placeholder}
                        {disabled}
                        oninput={handleInput}
                        onkeydown={handleKeyDown}
                        oncompositionstart={handleCompositionStart}
                        oncompositionend={handleCompositionEnd}
                        rows="1"
                        class="scrollbar-thin scrollbar-track-transparent scrollbar-thumb-white/20 hover:scrollbar-thumb-white/30 m-0 max-h-96 min-h-6 w-full resize-none overflow-y-auto border-0 bg-transparent px-1 py-0 font-[inherit] text-[0.9375rem] leading-6 text-white/96 outline-none placeholder:text-white/40"
                    ></textarea>
                </div>

                <div class="mr-1 flex shrink-0 items-center space-x-1">
                    <Tooltip.Root>
                        <Tooltip.Trigger>
                            {#if isGenerating}
                                <button
                                    type="button"
                                    aria-label="stop generating"
                                    class="flex h-8 w-8 items-center justify-center rounded-full bg-white text-black transition-all duration-200 hover:bg-gray-100 active:scale-95"
                                    onclick={onStop}
                                >
                                    <Stop className="h-3.5 w-3.5" />
                                </button>
                            {:else}
                                <button
                                    type="submit"
                                    aria-label="send message"
                                    class="flex h-8 w-8 items-center justify-center rounded-full transition-all duration-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 {!(
                                        value.trim() === '' || disabled
                                    )
                                        ? 'bg-white text-black hover:bg-gray-100'
                                        : 'bg-gray-200 text-gray-900'}"
                                    disabled={value.trim() === '' || disabled}
                                >
                                    <ArrowUp className="h-5 w-5" strokeWidth="2" />
                                </button>
                            {/if}
                        </Tooltip.Trigger>
                        <Tooltip.Content>
                            <p>{isGenerating ? 'stop generating' : 'send message'}</p>
                        </Tooltip.Content>
                    </Tooltip.Root>
                </div>
            </div>
        </div>
    </div>
</form>
