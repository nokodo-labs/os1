<script lang="ts">
    import type { Snippet } from 'svelte'

    interface Props {
        role: 'user' | 'assistant'
        content: string
        timestamp?: Date
        actions?: Snippet
    }

    let { role, content, timestamp, actions }: Props = $props()
    const isUser = $derived(role === 'user')
</script>

<div class="message-container" class:user={isUser} class:assistant={!isUser}>
    <div class="message-bubble liquid-glass">
        <div class="message-content">
            {content}
        </div>
        {#if timestamp}
            <div class="message-timestamp">
                {timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </div>
        {/if}
    </div>

    {#if actions}
        <div class="message-actions">
            {@render actions()}
        </div>
    {/if}
</div>

<style>
    .message-container {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        max-width: 80%;
        animation: messageSlideIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    }

    @keyframes messageSlideIn {
        from {
            opacity: 0;
            transform: translateY(10px) scale(0.95);
        }
        to {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
    }

    .message-container.user {
        align-self: flex-end;
        align-items: flex-end;
    }

    .message-container.assistant {
        align-self: flex-start;
        align-items: flex-start;
    }

    .message-bubble {
        position: relative;
        padding: 1rem 1.25rem;
        border-radius: 1.5rem;
        backdrop-filter: blur(20px) saturate(180%);
        transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    }

    .message-bubble::before {
        content: '';
        position: absolute;
        inset: 0;
        border-radius: inherit;
        padding: 1px;
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.4), rgba(255, 255, 255, 0.1));
        -webkit-mask:
            linear-gradient(#fff 0 0) content-box,
            linear-gradient(#fff 0 0);
        -webkit-mask-composite: xor;
        mask:
            linear-gradient(#fff 0 0) content-box,
            linear-gradient(#fff 0 0);
        mask-composite: exclude;
        pointer-events: none;
    }

    .message-bubble:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
    }

    .user .message-bubble {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.3), rgba(139, 92, 246, 0.2));
    }

    .assistant .message-bubble {
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.15), rgba(255, 255, 255, 0.05));
    }

    .message-content {
        color: rgba(255, 255, 255, 0.95);
        font-size: 0.95rem;
        line-height: 1.6;
        word-wrap: break-word;
    }

    .message-timestamp {
        margin-top: 0.5rem;
        font-size: 0.75rem;
        color: rgba(255, 255, 255, 0.5);
    }

    .message-actions {
        display: flex;
        gap: 0.5rem;
        padding: 0 0.5rem;
    }
</style>
