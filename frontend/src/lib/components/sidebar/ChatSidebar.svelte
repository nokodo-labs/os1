<script lang="ts">
    import * as ScrollArea from '$lib/components/ui/scroll-area'
    import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
    import { ChevronLeft, MessageSquare, MoreHorizontal, Search } from '@lucide/svelte'

    const sidebar = useSidebar() as any

    interface Chat {
        id: string
        title: string
        lastMessage: string
        timestamp: Date
    }

    // Demo data
    let chats = $state<Chat[]>([
        {
            id: '1',
            title: 'Building a sidebar component',
            lastMessage: 'Can you help me implement a sidebar?',
            timestamp: new Date(),
        },
        {
            id: '2',
            title: 'API Integration',
            lastMessage: 'How do I connect to the backend?',
            timestamp: new Date(Date.now() - 3600000),
        },
        {
            id: '3',
            title: 'Liquid UI Effects',
            lastMessage: 'Implementing glass morphism...',
            timestamp: new Date(Date.now() - 7200000),
        },
    ])

    let searchQuery = $state('')

    const filteredChats = $derived(
        chats.filter((chat) => chat.title.toLowerCase().includes(searchQuery.toLowerCase()))
    )

    function formatTime(date: Date): string {
        const now = new Date()
        const diff = now.getTime() - date.getTime()
        const hours = Math.floor(diff / 3600000)

        if (hours < 1) return 'Just now'
        if (hours < 24) return `${hours}h ago`
        return date.toLocaleDateString()
    }
</script>

<div
    class="chat-sidebar liquid-glass flex flex-col border-r border-white/10"
    class:collapsed={!sidebar.isChatSidebarOpen}
>
    {#if sidebar.isChatSidebarOpen}
        <!-- Header -->
        <div class="border-b border-white/10 p-4">
            <div class="mb-3 flex items-center justify-between">
                <h2 class="text-lg font-semibold text-white">Chats</h2>
                <button
                    class="close-button"
                    onclick={() => sidebar.toggleChatSidebar()}
                    aria-label="Close sidebar"
                >
                    <ChevronLeft class="h-4 w-4" />
                </button>
            </div>

            <!-- Search -->
            <div class="search-container">
                <span class="search-icon">
                    <Search class="h-4 w-4" />
                </span>
                <input
                    type="text"
                    placeholder="Search chats..."
                    bind:value={searchQuery}
                    class="search-input"
                />
            </div>
        </div>

        <!-- Chat List -->
        <ScrollArea.Root class="flex-1">
            <div class="space-y-1 p-2">
                {#if filteredChats.length === 0}
                    <div class="empty-state">
                        <MessageSquare class="mb-2 h-8 w-8 text-white/30" />
                        <p class="text-sm text-white/50">No chats found</p>
                    </div>
                {:else}
                    {#each filteredChats as chat (chat.id)}
                        <div class="chat-item-wrapper">
                            <button
                                class="chat-item"
                                class:active={sidebar.selectedChatId === chat.id}
                                onclick={() => sidebar.selectChat(chat.id)}
                            >
                                <div class="chat-item-content">
                                    <div class="chat-item-header">
                                        <h3 class="chat-title">{chat.title}</h3>
                                        <span class="chat-time">{formatTime(chat.timestamp)}</span>
                                    </div>
                                    <p class="chat-preview">{chat.lastMessage}</p>
                                </div>
                            </button>
                            <button class="chat-actions" onclick={(e) => e.stopPropagation()}>
                                <MoreHorizontal class="h-4 w-4" />
                            </button>
                        </div>
                    {/each}
                {/if}
            </div>
        </ScrollArea.Root>
    {/if}
</div>

<style>
    .chat-sidebar {
        position: relative;
        background: rgba(0, 0, 0, 0.2);
        backdrop-filter: blur(20px) saturate(180%);
        -webkit-backdrop-filter: blur(20px) saturate(180%);
        overflow: hidden;
        width: 16rem;
        transition:
            width 0.3s cubic-bezier(0.4, 0, 0.2, 1),
            opacity 0.3s ease,
            transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .chat-sidebar.collapsed {
        width: 0;
        opacity: 0;
        transform: translateX(-1rem);
        padding: 0;
    }

    .chat-sidebar::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: linear-gradient(
            180deg,
            rgba(255, 255, 255, 0.05) 0%,
            transparent 50%,
            rgba(0, 0, 0, 0.1) 100%
        );
        pointer-events: none;
    }

    .search-container {
        position: relative;
    }

    .search-icon {
        position: absolute;
        left: 0.75rem;
        top: 50%;
        transform: translateY(-50%);
        color: rgba(255, 255, 255, 0.5);
        pointer-events: none;
    }

    .search-input {
        width: 100%;
        padding: 0.5rem 0.75rem 0.5rem 2.5rem;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 0.5rem;
        color: white;
        font-size: 0.875rem;
        transition: all 0.2s ease;
    }

    .search-input::placeholder {
        color: rgba(255, 255, 255, 0.4);
    }

    .search-input:focus {
        outline: none;
        background: rgba(255, 255, 255, 0.08);
        border-color: rgba(255, 255, 255, 0.2);
        box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.05);
    }

    .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 3rem 1rem;
        text-align: center;
    }

    .chat-item-wrapper {
        position: relative;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .chat-item {
        position: relative;
        display: flex;
        align-items: center;
        flex: 1;
        width: 100%;
        padding: 0.75rem;
        border-radius: 0.75rem;
        background: transparent;
        border: 1px solid transparent;
        color: white;
        text-align: left;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .chat-item:hover {
        background: rgba(255, 255, 255, 0.05);
        border-color: rgba(255, 255, 255, 0.1);
    }

    .chat-item.active {
        background: rgba(255, 255, 255, 0.1);
        border-color: rgba(255, 255, 255, 0.15);
        box-shadow: inset 0 2px 8px rgba(255, 255, 255, 0.1);
    }

    .chat-item-content {
        flex: 1;
        min-width: 0;
    }

    .chat-item-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
        margin-bottom: 0.25rem;
    }

    .chat-title {
        font-size: 0.875rem;
        font-weight: 500;
        color: white;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .chat-time {
        font-size: 0.75rem;
        color: rgba(255, 255, 255, 0.5);
        flex-shrink: 0;
    }

    .chat-preview {
        font-size: 0.75rem;
        color: rgba(255, 255, 255, 0.6);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .chat-actions {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0.25rem;
        border-radius: 0.375rem;
        background: transparent;
        border: none;
        color: rgba(255, 255, 255, 0.5);
        opacity: 0;
        transition: all 0.2s ease;
        cursor: pointer;
        flex-shrink: 0;
    }

    .chat-item-wrapper:hover .chat-actions {
        opacity: 1;
    }

    .chat-actions:hover {
        background: rgba(255, 255, 255, 0.1);
        color: white;
    }

    .close-button {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.05);
        color: rgba(255, 255, 255, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.1);
        cursor: pointer;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .close-button:hover {
        background: rgba(255, 255, 255, 0.1);
        color: white;
        transform: scale(1.05);
    }
</style>
