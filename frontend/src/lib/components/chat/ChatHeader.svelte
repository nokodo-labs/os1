<script lang="ts">
    import type { Snippet } from 'svelte'

    interface Props {
        title?: string
        subtitle?: string
        actions?: Snippet
    }

    let { title = 'nokodo AI', subtitle, actions }: Props = $props()
</script>

<header class="chat-header liquid-glass">
    <div class="header-content">
        <div class="header-text">
            <h1 class="header-title">{title}</h1>
            {#if subtitle}
                <p class="header-subtitle">{subtitle}</p>
            {/if}
        </div>

        {#if actions}
            <div class="header-actions">
                {@render actions()}
            </div>
        {/if}
    </div>
</header>

<style>
    .chat-header {
        position: relative;
        padding: 1.25rem 1.5rem;
        backdrop-filter: blur(20px) saturate(180%);
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.05));
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        z-index: 10;
    }

    .chat-header::after {
        content: '';
        position: absolute;
        bottom: -1px;
        left: 0;
        right: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(139, 92, 246, 0.5), transparent);
        animation: glowPulse 3s ease-in-out infinite;
    }

    @keyframes glowPulse {
        0%,
        100% {
            opacity: 0.3;
        }
        50% {
            opacity: 0.8;
        }
    }

    .header-content {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
    }

    .header-text {
        flex: 1;
    }

    .header-title {
        font-size: 1.25rem;
        font-weight: 600;
        color: rgba(255, 255, 255, 0.95);
        margin: 0;
        background: linear-gradient(135deg, #a78bfa, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    .header-subtitle {
        font-size: 0.875rem;
        color: rgba(255, 255, 255, 0.6);
        margin: 0.25rem 0 0 0;
    }

    .header-actions {
        display: flex;
        gap: 0.75rem;
        align-items: center;
    }
</style>
