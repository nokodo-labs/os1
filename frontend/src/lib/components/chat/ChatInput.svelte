<script lang="ts">
    import { Send } from '@lucide/svelte'

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
    let mouseX = $state(50)
    let mouseY = $state(50)

    function handleMouseMove(event: MouseEvent) {
        const target = event.currentTarget as HTMLDivElement | null
        if (!target) return
        const rect = target.getBoundingClientRect()
        mouseX = Math.min(100, Math.max(0, ((event.clientX - rect.left) / rect.width) * 100))
        mouseY = Math.min(100, Math.max(0, ((event.clientY - rect.top) / rect.height) * 100))
    }

    function resetMouseGlow() {
        mouseX = 50
        mouseY = 50
    }

    function handleInput() {
        if (!textarea) return
        textarea.style.height = 'auto'
        textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }

    function handleKeyDown(event: KeyboardEvent) {
        if (event.key === 'Enter' && !event.shiftKey) {
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
</script>

<div class="chat-input">
    <div
        class="input-shell"
        onmousemove={handleMouseMove}
        onmouseleave={resetMouseGlow}
        role="textbox"
        tabindex="-1"
    >
        <div class="input-surface" style="--glow-x: {mouseX}%; --glow-y: {mouseY}%">
            <textarea
                bind:this={textarea}
                bind:value
                {placeholder}
                {disabled}
                oninput={handleInput}
                onkeydown={handleKeyDown}
                rows="1"
                class="input-field"
            ></textarea>

            <button
                class="send-button"
                type="button"
                onclick={handleSubmit}
                disabled={!value.trim() || disabled}
            >
                <Send class="icon" size={20} strokeWidth={2.5} />
            </button>
        </div>
    </div>
</div>

<style>
    .chat-input {
        position: relative;
        width: 100%;
    }

    .input-shell {
        position: relative;
        width: 100%;
        padding: 3px;
        border-radius: 24px;
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.16), rgba(255, 255, 255, 0.04));
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
        overflow: visible;
    }

    .input-shell::before {
        content: '';
        position: absolute;
        inset: 1px;
        border-radius: 23px;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0));
        opacity: 0.65;
        pointer-events: none;
        filter: blur(1px);
    }

    .input-shell:focus-within::before {
        opacity: 0.82;
    }

    .input-surface {
        position: relative;
        display: flex;
        align-items: flex-end;
        gap: 12px;
        padding: 16px 18px 16px 20px;
        border-radius: 21px;
        background: rgba(6, 8, 14, 0.82);
        backdrop-filter: blur(18px) saturate(185%);
        -webkit-backdrop-filter: blur(18px) saturate(185%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow:
            inset 0 1px 0 rgba(255, 255, 255, 0.12),
            inset 0 -1px 0 rgba(255, 255, 255, 0.05),
            0 18px 40px rgba(6, 8, 14, 0.6);
        overflow: hidden;
        transition:
            border 0.3s ease,
            box-shadow 0.3s ease,
            background 0.3s ease;
    }

    .input-shell:focus-within .input-surface {
        border-color: rgba(160, 200, 255, 0.35);
        box-shadow:
            inset 0 1px 0 rgba(255, 255, 255, 0.18),
            inset 0 -1px 0 rgba(255, 255, 255, 0.08),
            0 28px 60px rgba(12, 14, 24, 0.75);
        background: rgba(10, 12, 20, 0.88);
    }

    .input-surface::before {
        content: '';
        position: absolute;
        inset: 0;
        background: radial-gradient(
            circle at var(--glow-x, 50%) var(--glow-y, 50%),
            rgba(160, 200, 255, 0.18) 0%,
            rgba(60, 90, 160, 0.08) 18%,
            transparent 55%
        );
        pointer-events: none;
        opacity: 0;
        transition: opacity 0.3s ease;
    }

    .input-shell:hover .input-surface::before,
    .input-shell:focus-within .input-surface::before {
        opacity: 1;
    }

    .input-surface::after {
        content: '';
        position: absolute;
        top: -60%;
        left: -25%;
        width: 150%;
        height: 160%;
        background: linear-gradient(120deg, rgba(255, 255, 255, 0.18), transparent 58%);
        opacity: 0.4;
        pointer-events: none;
        transform: translate3d(0, 0, 0);
        transition: opacity 0.35s ease;
    }

    .input-shell:focus-within .input-surface::after {
        opacity: 0.55;
    }

    .input-field {
        flex: 1;
        min-height: 24px;
        max-height: 200px;
        padding: 0;
        margin: 0;
        background: transparent;
        border: none;
        outline: none;
        color: rgba(255, 255, 255, 0.96);
        font-size: 15px;
        font-weight: 400;
        line-height: 1.65;
        resize: none;
        position: relative;
        z-index: 1;
    }

    .input-field::placeholder {
        color: rgba(255, 255, 255, 0.38);
    }

    .input-field::-webkit-scrollbar {
        width: 6px;
    }

    .input-field::-webkit-scrollbar-track {
        background: transparent;
    }

    .input-field::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.18);
        border-radius: 3px;
    }

    .send-button {
        flex-shrink: 0;
        width: 38px;
        height: 38px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.14);
        background: linear-gradient(135deg, rgba(32, 34, 44, 0.95), rgba(20, 22, 30, 0.95));
        color: rgba(255, 255, 255, 0.88);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition:
            border 0.25s ease,
            background 0.25s ease,
            transform 0.2s ease,
            box-shadow 0.25s ease;
        backdrop-filter: blur(12px) saturate(160%);
        -webkit-backdrop-filter: blur(12px) saturate(160%);
    }

    .send-button:hover:not(:disabled) {
        transform: translateY(-1px);
        border-color: rgba(200, 220, 255, 0.35);
        background: linear-gradient(135deg, rgba(60, 68, 96, 0.95), rgba(24, 26, 34, 0.95));
        box-shadow:
            0 10px 24px rgba(15, 20, 35, 0.45),
            inset 0 1px 0 rgba(255, 255, 255, 0.15);
    }

    .send-button:active:not(:disabled) {
        transform: translateY(0);
        box-shadow: inset 0 1px 4px rgba(0, 0, 0, 0.4);
    }

    .send-button:disabled {
        opacity: 0.45;
        cursor: not-allowed;
    }

    .send-button :global(svg) {
        filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.45));
    }
</style>
