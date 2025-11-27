<script lang="ts">
    import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
    import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
    import LightBulb from '$lib/components/icons/LightBulb.svelte'
    import Plus from '$lib/components/icons/Plus.svelte'
    import XMark from '$lib/components/icons/XMark.svelte'
    import DOMPurify from 'dompurify'
    import { marked } from 'marked'
    import { onDestroy, onMount, tick } from 'svelte'
    import { fade, fly } from 'svelte/transition'

    interface Props {
        onAdd?: (messages: { role: 'user' | 'assistant'; content: string }[]) => void
    }

    let { onAdd }: Props = $props()

    let visible = $state(false)
    let position = $state({ top: 0, left: 0 })
    let selectedText = $state('')
    let mode = $state<'menu' | 'input' | 'response'>('menu')
    let inputValue = $state('')
    let responseContent = $state('')
    let isGenerating = $state(false)
    let container = $state<HTMLElement | null>(null)
    let inputElement = $state<HTMLInputElement | null>(null)

    let selectionTimeout: number

    function handleSelectionChange() {
        clearTimeout(selectionTimeout)
        selectionTimeout = window.setTimeout(() => {
            const selection = window.getSelection()

            // If we are interacting with the floating menu, don't hide it
            if (container && container.contains(document.activeElement)) {
                return
            }

            if (selection && selection.toString().trim().length > 0) {
                const range = selection.getRangeAt(0)
                const rect = range.getBoundingClientRect()

                // Check if selection is inside the floating menu itself to avoid loops
                if (container && container.contains(selection.anchorNode)) {
                    return
                }

                selectedText = selection.toString()

                // Only update position if we are not already visible or if we are in menu mode
                // This prevents the window from jumping around if the user selects text inside the response
                if (!visible || mode === 'menu') {
                    position = {
                        top: rect.bottom + 10,
                        left: rect.left + rect.width / 2,
                    }
                    visible = true
                    // Reset to menu mode if we were hidden
                    if (!visible) mode = 'menu'
                }
            } else {
                // Only hide if we are not in the middle of an interaction
                // But if selection is cleared, we usually want to hide the menu unless we are typing/viewing response
                // For now, let's hide it if selection is cleared, unless we are in input/response mode
                if (mode === 'menu') {
                    visible = false
                }
            }
        }, 100)
    }

    function handleMouseDown(e: MouseEvent) {
        if (container && !container.contains(e.target as Node)) {
            // Clicked outside
            if (mode === 'menu') {
                visible = false
            }
            // If in input/response mode, we might want to keep it open or close it?
            // Let's close it for now to be simple
            visible = false
            resetState()
        }
    }

    function resetState() {
        mode = 'menu'
        inputValue = ''
        responseContent = ''
        isGenerating = false
    }

    onMount(() => {
        document.addEventListener('selectionchange', handleSelectionChange)
        document.addEventListener('mousedown', handleMouseDown)
    })

    onDestroy(() => {
        document.removeEventListener('selectionchange', handleSelectionChange)
        document.removeEventListener('mousedown', handleMouseDown)
    })

    async function handleAsk() {
        mode = 'input'
        await tick()
        inputElement?.focus()
    }

    async function handleExplain() {
        mode = 'response'
        await generateResponse(`Explain this:\n\n${selectedText}`)
    }

    async function handleSubmitQuestion() {
        if (!inputValue.trim()) return
        const question = inputValue
        mode = 'response'
        await generateResponse(`${selectedText}\n\nQuestion: ${question}`)
    }

    async function generateResponse(prompt: string) {
        isGenerating = true
        responseContent = ''

        // Mock streaming response
        const mockResponse =
            'This is a simulated response. In a real implementation, this would call the backend API to stream the LLM response based on the selected text and your prompt.'
        const words = mockResponse.split(' ')

        for (const word of words) {
            await new Promise((r) => setTimeout(r, 50))
            responseContent += word + ' '
        }

        isGenerating = false
    }

    function handleAdd() {
        if (onAdd) {
            onAdd([
                {
                    role: 'user',
                    content: `Context: ${selectedText}\n\n${inputValue || 'Explain this.'}`,
                },
                { role: 'assistant', content: responseContent },
            ])
        }
        visible = false
        resetState()
        window.getSelection()?.removeAllRanges()
    }

    function close() {
        visible = false
        resetState()
    }

    // Parse markdown
    let parsedContent = $derived(DOMPurify.sanitize(marked.parse(responseContent) as string))
</script>

{#if visible}
    <div
        bind:this={container}
        class="fixed z-50 flex flex-col items-center"
        style="top: {position.top}px; left: {position.left}px; transform: translateX(-50%);"
        transition:fade={{ duration: 150 }}
    >
        {#if mode === 'menu'}
            <div
                class="liquid-glass--frosted flex items-center gap-1 rounded-xl p-1 transition-all"
            >
                <button
                    class="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors hover:bg-black/5 dark:hover:bg-white/10"
                    onclick={handleAsk}
                >
                    <ChatBubble className="size-3.5" />
                    Ask
                </button>
                <div class="h-4 w-px bg-black/10 dark:bg-white/10"></div>
                <button
                    class="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors hover:bg-black/5 dark:hover:bg-white/10"
                    onclick={handleExplain}
                >
                    <LightBulb className="size-3.5" />
                    Explain
                </button>
            </div>
        {:else if mode === 'input'}
            <div
                class="liquid-glass--frosted flex w-72 items-center gap-2 rounded-full p-1.5"
                transition:fly={{ y: 5, duration: 200 }}
            >
                <input
                    bind:this={inputElement}
                    type="text"
                    class="flex-1 bg-transparent px-3 text-sm placeholder-black/40 outline-none dark:text-white dark:placeholder-white/40"
                    placeholder="Ask a question..."
                    bind:value={inputValue}
                    onkeydown={(e) => e.key === 'Enter' && handleSubmitQuestion()}
                />
                <button
                    class="flex size-7 items-center justify-center rounded-full text-white transition-all hover:brightness-110 disabled:opacity-50 disabled:hover:brightness-100"
                    style="background-color: var(--accent-primary);"
                    onclick={handleSubmitQuestion}
                    disabled={!inputValue.trim()}
                >
                    <ArrowUp className="size-4" />
                </button>
            </div>
        {:else if mode === 'response'}
            <div
                class="liquid-glass--frosted flex w-80 flex-col gap-3 rounded-2xl p-4"
                transition:fly={{ y: 5, duration: 200 }}
            >
                <div
                    class="flex items-center justify-between border-b border-black/10 pb-2 dark:border-white/10"
                >
                    <span class="text-xs font-medium opacity-60">AI Response</span>
                    <button class="opacity-40 hover:opacity-100" onclick={close}>
                        <XMark className="size-3.5" />
                    </button>
                </div>

                <div
                    class="prose prose-sm dark:prose-invert max-h-60 overflow-y-auto text-xs leading-relaxed"
                >
                    {#if !responseContent && isGenerating}
                        <span class="animate-pulse opacity-40">Thinking...</span>
                    {:else}
                        <!-- eslint-disable-next-line svelte/no-at-html-tags -->
                        {@html parsedContent}
                    {/if}
                </div>

                {#if !isGenerating && responseContent}
                    <div class="flex justify-end pt-1">
                        <button
                            class="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-white transition-all hover:brightness-110"
                            style="background-color: var(--accent-primary);"
                            onclick={handleAdd}
                        >
                            <Plus className="size-3.5" />
                            Add to Chat
                        </button>
                    </div>
                {/if}
            </div>
        {/if}
    </div>
{/if}
