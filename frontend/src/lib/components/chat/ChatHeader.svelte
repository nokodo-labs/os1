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
    <span class="liquid-glass__highlight" aria-hidden="true"></span>

    <div class="liquid-glass__content header-content">
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
        margin: 1.25rem 2rem 0;
        padding: 1.25rem 1.75rem;
        box-shadow: 0 32px 64px rgba(12, 10, 30, 0.45);
    }

    .header-content {
        position: relative;
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
        background: linear-gradient(135deg, #cdbdff, #7c83ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    .header-subtitle {
        font-size: 0.875rem;
        color: rgba(225, 225, 255, 0.68);
        margin: 0.25rem 0 0 0;
    }

    .header-actions {
        display: flex;
        gap: 0.75rem;
        align-items: center;
    }
</style>
