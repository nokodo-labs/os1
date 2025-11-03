<script lang="ts">
    import * as Separator from '$lib/components/ui/separator'
    import * as Tooltip from '$lib/components/ui/tooltip'
    import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
    import { FileText, Home, MessageSquarePlus } from '@lucide/svelte'

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
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
    class="app-sidebar liquid-glass flex flex-col items-center gap-4 border-r border-white/10 px-2 py-6"
    class:collapsed={!sidebar.isOpen}
    onclick={(e) => {
        // Toggle if clicking on empty space (not on buttons or interactive elements)
        const target = e.target as HTMLElement
        const isClickOnButton = target.closest('button') || target.closest('[role="button"]')
        if (!isClickOnButton && !sidebar.isChatSidebarOpen) {
            sidebar.toggleChatSidebar()
        }
    }}
    role="complementary"
    aria-label="App sidebar"
>
    {#if sidebar.isOpen}
        <!-- Logo / Brand -->
        <div class="sidebar-item group relative">
            <button
                class="sidebar-button"
                onclick={(e) => {
                    e.stopPropagation()
                    if (!sidebar.isChatSidebarOpen) {
                        sidebar.toggleChatSidebar()
                    } else {
                        sidebar.selectChat(null)
                    }
                }}
                aria-label="Home"
            >
                <div class="logo-container">
                    <div class="liquid-orb"></div>
                </div>
            </button>
        </div>
        <Separator.Root class="w-8 bg-white/10" />

        <!-- Main Items -->
        <div class="flex flex-1 flex-col gap-2">
            {#each items as item (item.id)}
                {@const Icon = item.icon}
                <Tooltip.Root delayDuration={100}>
                    <Tooltip.Trigger>
                        <button
                            class="sidebar-button transition-transform duration-200 hover:scale-110"
                            onclick={item.action}
                            aria-label={item.label}
                        >
                            <Icon class="h-5 w-5" />
                        </button>
                    </Tooltip.Trigger>
                    <Tooltip.Content side="right" class="liquid-glass-tooltip">
                        <p>{item.label}</p>
                    </Tooltip.Content>
                </Tooltip.Root>
            {/each}
        </div>

        <!-- Bottom Items -->
        <div class="flex flex-col gap-2">
            <Separator.Root class="my-2 w-8 bg-white/10" />

            <!-- User Profile Section -->
            <Tooltip.Root delayDuration={100}>
                <Tooltip.Trigger>
                    <button
                        class="user-profile-button"
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
                    </button>
                </Tooltip.Trigger>
                <Tooltip.Content side="right" class="liquid-glass-tooltip">
                    <div class="user-tooltip">
                        <p class="font-semibold">{user.name}</p>
                        <p class="text-xs text-white/60">{user.email}</p>
                    </div>
                </Tooltip.Content>
            </Tooltip.Root>
        </div>
    {/if}
</div>

<style>
    .app-sidebar {
        position: relative;
        background: rgba(0, 0, 0, 0.3);
        backdrop-filter: blur(20px) saturate(180%);
        -webkit-backdrop-filter: blur(20px) saturate(180%);
        overflow: hidden;
        width: 4.5rem;
        transition:
            width 0.3s cubic-bezier(0.4, 0, 0.2, 1),
            opacity 0.3s ease;
    }

    .app-sidebar.collapsed {
        width: 0;
        opacity: 0;
        padding: 0;
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

    .sidebar-button {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 2.75rem;
        height: 2.75rem;
        border-radius: 1rem;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: rgba(255, 255, 255, 0.9);
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .sidebar-button:hover {
        background: rgba(255, 255, 255, 0.1);
        border-color: rgba(255, 255, 255, 0.2);
        box-shadow:
            0 4px 16px rgba(255, 255, 255, 0.1),
            inset 0 2px 8px rgba(255, 255, 255, 0.15);
    }

    .sidebar-button:active {
        transform: scale(0.95);
    }

    .logo-container {
        position: relative;
        width: 2rem;
        height: 2rem;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .liquid-orb {
        width: 2rem;
        height: 2rem;
        border-radius: 50%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        box-shadow:
            0 4px 12px rgba(102, 126, 234, 0.4),
            inset 0 2px 8px rgba(255, 255, 255, 0.3);
        animation: float 3s ease-in-out infinite;
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

    :global(.liquid-glass-tooltip) {
        background: rgba(0, 0, 0, 0.8) !important;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: white;
    }

    .user-profile-button {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 2.75rem;
        height: 2.75rem;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.05);
        border: 2px solid rgba(255, 255, 255, 0.15);
        cursor: pointer;
        transition: all 0.2s ease;
        overflow: hidden;
    }

    .user-profile-button:hover {
        border-color: rgba(139, 92, 246, 0.5);
        box-shadow:
            0 4px 16px rgba(139, 92, 246, 0.3),
            inset 0 2px 8px rgba(255, 255, 255, 0.15);
        transform: scale(1.05);
    }

    .user-profile-button:active {
        transform: scale(0.95);
    }

    .user-avatar {
        width: 100%;
        height: 100%;
        object-fit: cover;
        border-radius: 50%;
    }

    .user-avatar-placeholder {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%);
        color: white;
        font-size: 0.875rem;
        font-weight: 600;
        text-transform: uppercase;
    }

    .user-tooltip {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
    }
</style>
