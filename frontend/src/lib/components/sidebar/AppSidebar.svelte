<script lang="ts">
    import * as ScrollArea from '$lib/components/ui/scroll-area'
    import * as Separator from '$lib/components/ui/separator'
    import * as Tooltip from '$lib/components/ui/tooltip'
    import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
    import {
        ChevronLeft,
        FileText,
        Home,
        MessageSquare,
        MessageSquarePlus,
        MoreHorizontal,
        PanelLeft,
        Search,
    } from '@lucide/svelte'

    const sidebar = useSidebar() as any

    // User profile data (would come from auth context in production)
    const user = {
        name: 'Simone',
        email: 's.pipitone@nokodo.io',
        avatar: null, // URL to avatar image, or null for initials
    }

    function getUserInitials(name: string): string {
        return name
            .split(' ')
            .map((n) => n[0])
            .join('')
            .toUpperCase()
            .slice(0, 2)
    }

    function handleProfileClick() {
        // TODO: Open user profile modal/page
        console.log('Open user profile')
    }

    function handleSearchClick() {
        // TODO: Open global search overlay
        console.log('Open global search')
    }

    interface SidebarItem {
        id: string
        icon: typeof Home
        label: string
        action: () => void
    }

    const items: SidebarItem[] = [
        {
            id: 'home',
            icon: Home,
            label: 'Home',
            action: () => {
                sidebar.selectChat(null)
            },
        },
        {
            id: 'new-chat',
            icon: MessageSquarePlus,
            label: 'New Chat',
            action: () => {
                sidebar.selectChat(null)
                // TODO: Create new chat logic
            },
        },
        {
            id: 'notes',
            icon: FileText,
            label: 'Notes',
            action: () => {
                // TODO: Open notes view
                console.log('Open notes')
            },
        },
    ]

    // Demo chat data
    interface Chat {
        id: string
        title: string
        lastMessage: string
        timestamp: Date
    }

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

    function formatTime(date: Date): string {
        const now = new Date()
        const diff = now.getTime() - date.getTime()
        const hours = Math.floor(diff / 3600000)

        if (hours < 1) return 'Just now'
        if (hours < 24) return `${hours}h ago`
        return date.toLocaleDateString()
    }
</script>

<div class="app-sidebar liquid-glass" class:expanded={sidebar.isChatSidebarOpen}>
    <!-- Clickable overlay quando sidebar è chiusa -->
    {#if !sidebar.isChatSidebarOpen}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div class="sidebar-overlay" onclick={() => sidebar.toggleChatSidebar()}></div>
    {/if}

    <div class="sidebar-content">
        <!-- Logo / Brand with Close Button -->
        <div class="logo-section">
            <button
                class="sidebar-button logo-button"
                onclick={() => {
                    if (!sidebar.isChatSidebarOpen) {
                        sidebar.toggleChatSidebar()
                    }
                    sidebar.selectChat(null)
                }}
                aria-label="Home"
            >
                <div class="logo-container">
                    <div class="liquid-orb">
                        {#if !sidebar.isChatSidebarOpen}
                            <div class="orb-icon">
                                <PanelLeft class="h-4 w-4" />
                            </div>
                        {/if}
                    </div>
                    {#if sidebar.isChatSidebarOpen}
                        <img
                            src="https://nokodo.net/media/images/logo_full.svg"
                            alt="nokodo logo"
                            class="nokodo-logo"
                        />
                    {/if}
                </div>
            </button>

            <!-- Close button (only when expanded) -->
            {#if sidebar.isChatSidebarOpen}
                <button
                    class="close-button"
                    onclick={() => sidebar.toggleChatSidebar()}
                    aria-label="Close sidebar"
                >
                    <ChevronLeft class="h-5 w-5" />
                </button>
            {/if}
        </div>

        <Separator.Root class="bg-white/10" />

        <!-- Search -->
        <Tooltip.Root delayDuration={300} disabled={sidebar.isChatSidebarOpen}>
            <Tooltip.Trigger>
                {#snippet child({ props })}
                    <button
                        {...props}
                        class="sidebar-button"
                        onclick={handleSearchClick}
                        aria-label="Search"
                    >
                        <Search class="h-5 w-5" />
                        {#if sidebar.isChatSidebarOpen}
                            <span class="button-label">Search</span>
                        {/if}
                    </button>
                {/snippet}
            </Tooltip.Trigger>
            {#if !sidebar.isChatSidebarOpen}
                <Tooltip.Content side="right" class="tooltip-content">
                    <p>Search</p>
                </Tooltip.Content>
            {/if}
        </Tooltip.Root>

        <!-- Main Actions -->
        {#each items as item (item.id)}
            {@const Icon = item.icon}
            <Tooltip.Root delayDuration={300} disabled={sidebar.isChatSidebarOpen}>
                <Tooltip.Trigger>
                    {#snippet child({ props })}
                        <button
                            {...props}
                            class="sidebar-button"
                            onclick={item.action}
                            aria-label={item.label}
                        >
                            <Icon class="h-5 w-5" />
                            {#if sidebar.isChatSidebarOpen}
                                <span class="button-label">{item.label}</span>
                            {/if}
                        </button>
                    {/snippet}
                </Tooltip.Trigger>
                {#if !sidebar.isChatSidebarOpen}
                    <Tooltip.Content side="right" class="tooltip-content">
                        <p>{item.label}</p>
                    </Tooltip.Content>
                {/if}
            </Tooltip.Root>
        {/each}

        <!-- Chats Section (only when expanded) -->
        {#if sidebar.isChatSidebarOpen}
            <Separator.Root class="my-2 bg-white/10" />

            <div class="chats-section">
                <h3 class="section-title">Chats</h3>
                <ScrollArea.Root class="h-full">
                    <div class="space-y-1">
                        {#each chats as chat (chat.id)}
                            <div class="chat-item-wrapper">
                                <div
                                    class="chat-item"
                                    class:active={sidebar.selectedChatId === chat.id}
                                    onclick={() => sidebar.selectChat(chat.id)}
                                    role="button"
                                    tabindex="0"
                                    onkeydown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            sidebar.selectChat(chat.id)
                                        }
                                    }}
                                >
                                    <div class="chat-item-content">
                                        <div class="chat-item-header">
                                            <MessageSquare class="h-4 w-4 shrink-0" />
                                            <span class="chat-title">{chat.title}</span>
                                        </div>
                                        <span class="chat-time">{formatTime(chat.timestamp)}</span>
                                    </div>
                                </div>
                                <button
                                    class="chat-actions"
                                    onclick={(e) => {
                                        e.stopPropagation()
                                        console.log('Chat actions for', chat.id)
                                    }}
                                >
                                    <MoreHorizontal class="h-4 w-4" />
                                </button>
                            </div>
                        {/each}
                    </div>
                </ScrollArea.Root>
            </div>
        {/if}

        <Separator.Root class="bg-white/10" />

        <!-- User Profile -->
        <button
            class="sidebar-button user-profile-button"
            onclick={handleProfileClick}
            aria-label="User Profile"
        >
            {#if user.avatar}
                <img src={user.avatar} alt={user.name} class="user-avatar" />
            {:else}
                <div class="user-avatar-placeholder">
                    {getUserInitials(user.name)}
                </div>
            {/if}
            {#if sidebar.isChatSidebarOpen}
                <div class="user-info">
                    <p class="user-name">{user.name}</p>
                    <p class="user-email">{user.email}</p>
                </div>
            {/if}
        </button>
    </div>
</div>

<style>
    .app-sidebar {
        position: relative;
        background: rgba(0, 0, 0, 0.3);
        backdrop-filter: blur(20px) saturate(180%);
        -webkit-backdrop-filter: blur(20px) saturate(180%);
        width: 4.5rem;
        height: 100vh;
        transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        border-right: 1px solid rgba(255, 255, 255, 0.1);
    }

    .app-sidebar.expanded {
        width: 18rem;
    }

    .app-sidebar::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: linear-gradient(
            135deg,
            rgba(255, 255, 255, 0.1) 0%,
            rgba(255, 255, 255, 0.05) 50%,
            transparent 100%
        );
        pointer-events: none;
    }

    .sidebar-overlay {
        position: absolute;
        inset: 0;
        z-index: 10;
        cursor: pointer;
    }

    .sidebar-overlay:hover {
        background: rgba(255, 255, 255, 0.02);
    }

    .sidebar-content {
        position: relative;
        height: 100%;
        z-index: 20;
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 1rem 0.5rem;
        gap: 0.5rem;
        pointer-events: none;
    }

    .sidebar-content > * {
        pointer-events: auto;
    }

    .logo-section {
        display: flex;
        align-items: center;
        justify-content: space-between;
        width: 100%;
        gap: 0.5rem;
    }

    .app-sidebar:not(.expanded) .logo-section {
        justify-content: center;
    }

    .app-sidebar.expanded .logo-section .logo-button {
        flex: 1;
        max-width: calc(100% - 2.5rem);
    }

    .sidebar-button {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 3rem;
        height: 3rem;
        border-radius: 0.75rem;
        background: transparent;
        border: 1px solid transparent;
        color: white;
        cursor: pointer;
        transition: all 0.2s ease;
        flex-shrink: 0;
    }

    .expanded .sidebar-button {
        width: 100%;
        justify-content: flex-start;
        gap: 0.75rem;
        padding: 0 0.75rem;
    }

    .sidebar-button:hover {
        background: rgba(255, 255, 255, 0.05);
        border-color: rgba(255, 255, 255, 0.1);
    }

    .logo-button {
        padding: 0.5rem;
    }

    .logo-container {
        position: relative;
        display: flex;
        align-items: center;
        gap: 0.75rem;
        flex-shrink: 0;
    }

    .liquid-orb {
        position: relative;
        width: 2rem;
        height: 2rem;
        border-radius: 50%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        box-shadow:
            0 4px 12px rgba(102, 126, 234, 0.4),
            inset 0 2px 8px rgba(255, 255, 255, 0.3);
        animation: float 3s ease-in-out infinite;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.3s ease;
    }

    .orb-icon {
        position: absolute;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        opacity: 0;
        transform: scale(0.8);
        transition: all 0.3s ease;
    }

    .logo-button:hover .liquid-orb {
        background: linear-gradient(135deg, #7c8ef6 0%, #8b5cf6 100%);
        box-shadow:
            0 6px 16px rgba(102, 126, 234, 0.6),
            inset 0 2px 8px rgba(255, 255, 255, 0.4);
    }

    .logo-button:hover .orb-icon {
        opacity: 1;
        transform: scale(1);
    }

    @keyframes float {
        0%,
        100% {
            transform: translateY(0px);
        }
        50% {
            transform: translateY(-4px);
        }
    }

    .nokodo-logo {
        height: 1.75rem;
        width: auto;
        object-fit: contain;
        margin-left: 0.25rem;
        transform: translateY(-5px);
    }

    .button-label {
        font-size: 0.875rem;
        font-weight: 500;
        white-space: nowrap;
        opacity: 0;
        transition: opacity 0.3s ease 0.1s;
    }

    .app-sidebar.expanded .button-label {
        opacity: 1;
    }

    .close-button {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 2rem;
        height: 2rem;
        border-radius: 0.5rem;
        background: transparent;
        border: 1px solid transparent;
        color: rgba(255, 255, 255, 0.7);
        cursor: pointer;
        transition: all 0.2s ease;
        flex-shrink: 0;
    }

    .close-button:hover {
        background: rgba(255, 255, 255, 0.05);
        border-color: rgba(255, 255, 255, 0.1);
        color: white;
    }

    .chats-section {
        flex: 1;
        width: 100%;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        overflow: hidden;
        padding: 0 0.5rem;
        opacity: 0;
        transition: opacity 0.3s ease 0.1s;
    }

    .app-sidebar.expanded .chats-section {
        opacity: 1;
    }

    .section-title {
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        color: rgba(255, 255, 255, 0.5);
        padding: 0 0.75rem;
        margin-bottom: 0.25rem;
    }

    .chat-item-wrapper {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        position: relative;
    }

    .chat-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
        flex: 1;
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
        gap: 0.5rem;
        margin-bottom: 0.25rem;
    }

    .chat-title {
        font-size: 0.875rem;
        font-weight: 500;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .chat-time {
        font-size: 0.75rem;
        color: rgba(255, 255, 255, 0.5);
    }

    .chat-actions {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 2rem;
        height: 2rem;
        border-radius: 0.5rem;
        background: transparent;
        border: 1px solid transparent;
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

    .user-profile-button {
        margin-top: auto;
        border: 1px solid transparent;
        background: transparent;
    }

    .user-profile-button:hover {
        background: rgba(255, 255, 255, 0.05);
        border-color: rgba(255, 255, 255, 0.1);
    }

    .app-sidebar:not(.expanded) .user-profile-button {
        justify-content: center;
        width: 3rem;
        height: 3rem;
        padding: 0.5rem;
    }

    .app-sidebar.expanded .user-profile-button {
        justify-content: flex-start;
        width: 100%;
        gap: 0.75rem;
    }

    .user-avatar-placeholder {
        width: 2.25rem;
        height: 2.25rem;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%);
        color: white;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        border-radius: 50%;
        flex-shrink: 0;
        transition: all 0.2s ease;
    }

    .app-sidebar:not(.expanded) .user-avatar-placeholder {
        width: 2rem;
        height: 2rem;
        font-size: 0.7rem;
    }

    .user-info {
        display: flex;
        flex-direction: column;
        min-width: 0;
        text-align: left;
        opacity: 0;
        transition: opacity 0.3s ease 0.1s;
    }

    .app-sidebar.expanded .user-info {
        opacity: 1;
    }

    .user-name {
        font-size: 0.875rem;
        font-weight: 600;
        color: white;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .user-email {
        font-size: 0.75rem;
        color: rgba(255, 255, 255, 0.6);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    :global(.tooltip-content) {
        background: rgba(0, 0, 0, 0.9);
        color: white;
        padding: 0.5rem 0.75rem;
        border-radius: 0.5rem;
        font-size: 0.875rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    }
</style>
