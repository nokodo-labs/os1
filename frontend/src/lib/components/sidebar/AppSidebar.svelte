<script lang="ts">
    import { goto } from '$app/navigation'
    import { resolve } from '$app/paths'
    import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
    import ChatPlus from '$lib/components/icons/ChatPlus.svelte'
    import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
    import Document from '$lib/components/icons/Document.svelte'
    import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
    import Home from '$lib/components/icons/Home.svelte'
    import Search from '$lib/components/icons/Search.svelte'
    import Sidebar from '$lib/components/icons/Sidebar.svelte'
    import * as ScrollArea from '$lib/components/ui/scroll-area'
    import * as Separator from '$lib/components/ui/separator'
    import * as Tooltip from '$lib/components/ui/tooltip'
    import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
    import UserProfileTrigger from './UserProfileTrigger.svelte'
    const sidebar = useSidebar() as any
    // User profile data (would come from auth context in production)
    const user = {
        name: 'admin',
        email: 'admin@nokodo.net',
        avatar: null, // URL to avatar image, or null for initials
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
            label: 'home',
            action: () => {
                sidebar.selectChat(null)

                const start = (
                    document as unknown as {
                        startViewTransition?: (cb: () => Promise<void> | void) => void
                    }
                ).startViewTransition

                if (start) {
                    start.call(document, async () => {
                        await goto(resolve('/'), { keepFocus: true, noScroll: true })
                    })
                } else {
                    goto(resolve('/'), { keepFocus: true, noScroll: true })
                }
            },
        },
        {
            id: 'new-chat',
            icon: ChatPlus,
            label: 'new chat',
            action: () => {
                sidebar.selectChat(null)

                const start = (
                    document as unknown as {
                        startViewTransition?: (cb: () => Promise<void> | void) => void
                    }
                ).startViewTransition

                if (start) {
                    start.call(document, async () => {
                        await goto(resolve('/'), { keepFocus: true, noScroll: true })
                    })
                } else {
                    goto(resolve('/'), { keepFocus: true, noScroll: true })
                }
            },
        },
        {
            id: 'notes',
            icon: Document,
            label: 'notes',
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
        if (hours < 1) return 'just now'
        if (hours < 24) return `${hours}h ago`
        return date.toLocaleDateString()
    }
</script>

<div
    class="relative backdrop-blur-[20px] backdrop-saturate-180 {sidebar.isChatSidebarOpen
        ? 'w-72'
        : 'w-18'} h-screen rounded-none border-r border-white/10 transition-[width] duration-300 ease-in-out"
    style="background-color: var(--accent-bg);"
>
    <!-- Gradient overlay (replaces ::before pseudo-element) -->
    <div
        class="pointer-events-none absolute inset-0 bg-linear-to-br from-white/10 via-white/5 to-transparent"
    ></div>

    <!-- Clickable overlay quando sidebar è chiusa -->
    {#if !sidebar.isChatSidebarOpen}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
            class="absolute inset-0 z-10 cursor-pointer hover:bg-white/2"
            onclick={() => sidebar.toggleChatSidebar()}
        ></div>
    {/if}

    <div
        class="pointer-events-none relative z-20 flex h-full flex-col items-center gap-2 px-2 py-4 *:pointer-events-auto"
    >
        <!-- Logo / Brand with Close Button -->
        <div
            class="flex items-center {sidebar.isChatSidebarOpen
                ? 'justify-between'
                : 'justify-center'} w-full gap-2"
        >
            <button
                class="group relative flex items-center justify-center {sidebar.isChatSidebarOpen
                    ? 'max-w-[calc(100%-2.5rem)] flex-1'
                    : ''} h-12 w-12 shrink-0 cursor-pointer rounded-xl border border-transparent bg-transparent p-2 text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5"
                onclick={() => {
                    if (!sidebar.isChatSidebarOpen) {
                        sidebar.toggleChatSidebar()
                    }
                    sidebar.selectChat(null)
                }}
                aria-label="Home"
            >
                <div class="relative flex shrink-0 items-center gap-3">
                    <div
                        class="relative flex h-8 w-8 shrink-0 animate-[bounce_2s_ease-in-out_infinite] items-center justify-center rounded-full shadow-[0_4px_12px_var(--accent-shadow),inset_0_2px_8px_rgba(255,255,255,0.3)] transition-[background,box-shadow] duration-300 group-hover:shadow-[0_6px_16px_var(--accent-shadow),inset_0_2px_8px_rgba(255,255,255,0.4)]"
                        style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-secondary));"
                    >
                        {#if !sidebar.isChatSidebarOpen}
                            <div
                                class="absolute flex scale-75 items-center justify-center text-white opacity-0 transition-all duration-300 group-hover:scale-100 group-hover:opacity-100"
                            >
                                <Sidebar className="h-4 w-4" />
                            </div>
                        {/if}
                    </div>
                    {#if sidebar.isChatSidebarOpen}
                        <img
                            src="https://nokodo.net/media/images/logo_full.svg"
                            alt="nokodo logo"
                            class="ml-1 h-7 w-auto -translate-y-[5px] object-contain"
                        />
                    {/if}
                </div>
            </button>

            <!-- Close button (only when expanded) -->
            {#if sidebar.isChatSidebarOpen}
                <button
                    class="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-transparent bg-transparent text-white/70 transition-all duration-200 hover:border-white/10 hover:bg-white/5 hover:text-white"
                    onclick={() => sidebar.toggleChatSidebar()}
                    aria-label="Close sidebar"
                >
                    <ChevronLeft className="h-5 w-5" />
                </button>
            {/if}
        </div>

        <Separator.Root class="bg-white/10" />

        <!-- Search -->
        <Tooltip.Root delayDuration={300} disabled={sidebar.isChatSidebarOpen}>
            <Tooltip.Trigger>
                {#snippet child({ props }: { props: Record })}
                    <button
                        {...props}
                        class="relative flex items-center {sidebar.isChatSidebarOpen
                            ? 'w-full justify-start gap-3 px-3'
                            : 'w-12 justify-center'} h-12 shrink-0 cursor-pointer rounded-xl border border-transparent bg-transparent text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5"
                        onclick={handleSearchClick}
                        aria-label="Search"
                    >
                        <Search className="h-5 w-5" />
                        {#if sidebar.isChatSidebarOpen}
                            <span
                                class="text-sm font-medium whitespace-nowrap opacity-0 transition-opacity delay-100 duration-300 {sidebar.isChatSidebarOpen
                                    ? 'opacity-100'
                                    : ''}">search</span
                            >
                        {/if}
                    </button>
                {/snippet}
            </Tooltip.Trigger>
            {#if !sidebar.isChatSidebarOpen}
                <Tooltip.Content
                    side="right"
                    class="rounded-lg border border-white/10 bg-black/90 px-3 py-2 text-sm text-white shadow-[0_4px_12px_rgba(0,0,0,0.3)]"
                >
                    <p>search</p>
                </Tooltip.Content>
            {/if}
        </Tooltip.Root>

        <!-- Main Actions -->
        {#each items as item (item.id)}
            {@const Icon = item.icon}
            <Tooltip.Root delayDuration={300} disabled={sidebar.isChatSidebarOpen}>
                <Tooltip.Trigger>
                    {#snippet child({ props }: { props: Record })}
                        <button
                            {...props}
                            class="relative flex items-center {sidebar.isChatSidebarOpen
                                ? 'w-full justify-start gap-3 px-3'
                                : 'w-12 justify-center'} h-12 shrink-0 cursor-pointer rounded-xl border border-transparent bg-transparent text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5"
                            onclick={item.action}
                            aria-label={item.label}
                        >
                            <Icon className="h-5 w-5" />
                            {#if sidebar.isChatSidebarOpen}
                                <span
                                    class="text-sm font-medium whitespace-nowrap opacity-0 transition-opacity delay-100 duration-300 {sidebar.isChatSidebarOpen
                                        ? 'opacity-100'
                                        : ''}">{item.label}</span
                                >
                            {/if}
                        </button>
                    {/snippet}
                </Tooltip.Trigger>
                {#if !sidebar.isChatSidebarOpen}
                    <Tooltip.Content
                        side="right"
                        class="rounded-lg border border-white/10 bg-black/90 px-3 py-2 text-sm text-white shadow-[0_4px_12px_rgba(0,0,0,0.3)]"
                    >
                        <p>{item.label}</p>
                    </Tooltip.Content>
                {/if}
            </Tooltip.Root>
        {/each}

        <!-- Chats Section (only when expanded) -->
        {#if sidebar.isChatSidebarOpen}
            <Separator.Root class="my-2 bg-white/10" />
            <div
                class="flex w-full flex-1 flex-col gap-2 overflow-hidden px-2 opacity-0 transition-opacity delay-100 duration-300 {sidebar.isChatSidebarOpen
                    ? 'opacity-100'
                    : ''}"
            >
                <h3 class="mb-1 px-3 text-xs font-semibold text-white/50 uppercase">chats</h3>
                <ScrollArea.Root class="h-full">
                    <div class="space-y-1">
                        {#each chats as chat (chat.id)}
                            <div class="group/chat relative flex items-center gap-2">
                                <div
                                    class="flex flex-1 cursor-pointer items-center justify-between gap-2 rounded-xl border border-transparent bg-transparent p-3 text-left text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5 {sidebar.selectedChatId ===
                                    chat.id
                                        ? 'shadow-[inset_0_2px_8px_rgba(255,255,255,0.1)]'
                                        : ''}"
                                    style={sidebar.selectedChatId === chat.id
                                        ? 'background-color: var(--accent-bg); border-color: var(--accent-border);'
                                        : ''}
                                    onclick={() => sidebar.selectChat(chat.id)}
                                    role="button"
                                    tabindex="0"
                                    onkeydown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            sidebar.selectChat(chat.id)
                                        }
                                    }}
                                >
                                    <div class="min-w-0 flex-1">
                                        <div class="mb-1 flex items-center gap-2">
                                            <ChatBubble className="h-4 w-4 shrink-0" />
                                            <span
                                                class="overflow-hidden text-sm font-medium text-ellipsis whitespace-nowrap"
                                                >{chat.title}</span
                                            >
                                        </div>
                                        <span class="text-xs text-white/50"
                                            >{formatTime(chat.timestamp)}</span
                                        >
                                    </div>
                                </div>
                                <button
                                    class="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-transparent bg-transparent text-white/50 opacity-0 transition-all duration-200 group-hover/chat:opacity-100 hover:bg-white/10 hover:text-white"
                                    onclick={(e) => {
                                        e.stopPropagation()
                                        console.log('Chat actions for', chat.id)
                                    }}
                                >
                                    <EllipsisHorizontal className="h-4 w-4" />
                                </button>
                            </div>
                        {/each}
                    </div>
                </ScrollArea.Root>
            </div>
        {/if}

        <Separator.Root class="bg-white/10" />

        <!-- User Profile -->
        <UserProfileTrigger {user} isExpanded={sidebar.isChatSidebarOpen} />
    </div>
</div>

<style>
    @keyframes float {
        0%,
        100% {
            transform: translateY(0px);
        }
        50% {
            transform: translateY(-10px);
        }
    }
</style>
