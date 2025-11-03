<script lang="ts">
    import type { Snippet } from 'svelte'

    interface Props {
        variant?: 'primary' | 'secondary' | 'ghost'
        size?: 'sm' | 'md' | 'lg'
        disabled?: boolean
        onclick?: () => void
        children: Snippet
    }

    let {
        variant = 'secondary',
        size = 'md',
        disabled = false,
        onclick,
        children,
    }: Props = $props()
</script>

<button
    class="liquid-button"
    class:primary={variant === 'primary'}
    class:secondary={variant === 'secondary'}
    class:ghost={variant === 'ghost'}
    class:sm={size === 'sm'}
    class:md={size === 'md'}
    class:lg={size === 'lg'}
    {disabled}
    {onclick}
>
    {@render children()}
</button>

<style>
    .liquid-button {
        position: relative;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        border: none;
        border-radius: 0.75rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        backdrop-filter: blur(10px);
        overflow: hidden;
    }

    .liquid-button::before {
        content: '';
        position: absolute;
        inset: 0;
        border-radius: inherit;
        padding: 1px;
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.3), rgba(255, 255, 255, 0.1));
        -webkit-mask:
            linear-gradient(#fff 0 0) content-box,
            linear-gradient(#fff 0 0);
        -webkit-mask-composite: xor;
        mask:
            linear-gradient(#fff 0 0) content-box,
            linear-gradient(#fff 0 0);
        mask-composite: exclude;
        pointer-events: none;
        opacity: 0;
        transition: opacity 0.3s ease;
    }

    .liquid-button:hover::before {
        opacity: 1;
    }

    /* Sizes */
    .liquid-button.sm {
        padding: 0.375rem 0.75rem;
        font-size: 0.875rem;
    }

    .liquid-button.md {
        padding: 0.5rem 1rem;
        font-size: 0.9375rem;
    }

    .liquid-button.lg {
        padding: 0.75rem 1.5rem;
        font-size: 1rem;
    }

    /* Variants */
    .liquid-button.primary {
        background: linear-gradient(135deg, rgba(139, 92, 246, 0.8), rgba(99, 102, 241, 0.7));
        color: rgba(255, 255, 255, 0.95);
        box-shadow: 0 4px 20px rgba(139, 92, 246, 0.3);
    }

    .liquid-button.primary:hover:not(:disabled) {
        transform: translateY(-2px);
        box-shadow: 0 8px 32px rgba(139, 92, 246, 0.4);
    }

    .liquid-button.secondary {
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.15), rgba(255, 255, 255, 0.05));
        color: rgba(255, 255, 255, 0.9);
    }

    .liquid-button.secondary:hover:not(:disabled) {
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.2), rgba(255, 255, 255, 0.1));
        transform: translateY(-2px);
    }

    .liquid-button.ghost {
        background: transparent;
        color: rgba(255, 255, 255, 0.7);
    }

    .liquid-button.ghost:hover:not(:disabled) {
        background: rgba(255, 255, 255, 0.1);
        color: rgba(255, 255, 255, 0.95);
    }

    .liquid-button:active:not(:disabled) {
        transform: translateY(0) scale(0.98);
    }

    .liquid-button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
</style>
