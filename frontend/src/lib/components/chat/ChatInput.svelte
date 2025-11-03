<script lang="ts">
    import ArrowUpCircle from '$lib/components/icons/ArrowUpCircle.svelte'
    import Plus from '$lib/components/icons/Plus.svelte'
    import * as Tooltip from '$lib/components/ui/tooltip'

    interface ChatInputProps {
        value?: string
        placeholder?: string
        disabled?: boolean
        onSubmit?: (message: string) => void
    }

    let {
        value = $bindable(''),
        placeholder = 'Message nokodo AI...',
        disabled = false,
        onSubmit,
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
</script>

<div class="relative w-full">
    <div
        class="liquid-glass relative w-full rounded-3xl bg-[rgba(10,12,20,0.65)] transition-all duration-300 ease-in-out focus-within:shadow-[0px_6px_24px_rgba(0,0,0,0.3),0_0_0_1px_rgba(255,255,255,0.15)]"
    >
        <div class="liquid-glass__highlight"></div>
        <div class="liquid-glass__content flex min-h-14 items-end gap-3 px-4 py-3.5">
            <div class="flex shrink-0 items-center gap-2">
                <Tooltip.Root>
                    <Tooltip.Trigger>
                        <button
                            type="button"
                            class="relative inline-flex h-8 w-8 items-center justify-center rounded-lg border-0 bg-transparent p-0 text-white/65 transition-all duration-200 before:absolute before:inset-0 before:rounded-[inherit] before:bg-white/5 before:opacity-0 before:transition-opacity before:duration-200 hover:text-white/95 hover:before:opacity-100 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
                            {disabled}
                        >
                            <Plus className="w-5 h-5" strokeWidth="2" />
                        </button>
                    </Tooltip.Trigger>
                    <Tooltip.Content>
                        <p>Add attachment</p>
                    </Tooltip.Content>
                </Tooltip.Root>
            </div>

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
                class="scrollbar-thin scrollbar-track-transparent scrollbar-thumb-white/20 hover:scrollbar-thumb-white/30 m-0 max-h-50 min-h-6 flex-1 resize-none overflow-y-auto border-0 bg-transparent py-1 font-[inherit] text-[0.9375rem] leading-6 text-white/96 outline-none placeholder:text-white/40"
            ></textarea>

            <div class="flex shrink-0 items-center gap-2">
                <Tooltip.Root>
                    <Tooltip.Trigger>
                        <button
                            type="button"
                            class="relative inline-flex h-8 w-8 items-center justify-center rounded-lg border-0 bg-transparent p-0 text-white/65 transition-all duration-200 before:absolute before:inset-0 before:rounded-[inherit] before:bg-white/5 before:opacity-0 before:transition-opacity before:duration-200 hover:text-white/95 hover:before:opacity-100 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
                            disabled={!value.trim() || disabled}
                            onclick={handleSubmit}
                        >
                            <ArrowUpCircle className="w-5 h-5" strokeWidth="2" />
                        </button>
                    </Tooltip.Trigger>
                    <Tooltip.Content>
                        <p>Send message</p>
                    </Tooltip.Content>
                </Tooltip.Root>
            </div>
        </div>
    </div>
</div>
