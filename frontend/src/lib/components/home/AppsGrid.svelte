<script lang="ts">
    import Bolt from '$lib/components/icons/Bolt.svelte'
    import Bookmark from '$lib/components/icons/Bookmark.svelte'
    import Calendar from '$lib/components/icons/Calendar.svelte'
    import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
    import CheckBox from '$lib/components/icons/CheckBox.svelte'
    import Cloud from '$lib/components/icons/Cloud.svelte'
    import Cog6 from '$lib/components/icons/Cog6.svelte'
    import Database from '$lib/components/icons/Database.svelte'
    import Document from '$lib/components/icons/Document.svelte'
    import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
    import Heart from '$lib/components/icons/Heart.svelte'
    import Map from '$lib/components/icons/Map.svelte'
    import Photo from '$lib/components/icons/Photo.svelte'
    import Sparkles from '$lib/components/icons/Sparkles.svelte'
    import Star from '$lib/components/icons/Star.svelte'
    import Terminal from '$lib/components/icons/Terminal.svelte'
    import Users from '$lib/components/icons/Users.svelte'
    import { onDestroy } from 'svelte'

    type IconComponent = typeof Document

    interface AppDefinition {
        id: string
        title: string
        icon: IconComponent
    }

    const apps: AppDefinition[] = [
        { id: 'notes', title: 'notes', icon: Document },
        { id: 'reminders', title: 'reminders', icon: CheckBox },
        { id: 'calendar', title: 'calendar', icon: Calendar },
        { id: 'messages', title: 'messages', icon: ChatBubbles },
        { id: 'bookmarks', title: 'bookmarks', icon: Bookmark },
        { id: 'automations', title: 'automations', icon: Bolt },
        { id: 'cloud', title: 'cloud', icon: Cloud },
        { id: 'settings', title: 'settings', icon: Cog6 },
        { id: 'database', title: 'database', icon: Database },
        { id: 'world', title: 'world', icon: GlobeAlt },
        { id: 'photos', title: 'photos', icon: Photo },
        { id: 'maps', title: 'maps', icon: Map },
        { id: 'spark', title: 'spark', icon: Sparkles },
        { id: 'favorites', title: 'favorites', icon: Star },
        { id: 'health', title: 'health', icon: Heart },
        { id: 'terminal', title: 'terminal', icon: Terminal },
        { id: 'teams', title: 'teams', icon: Users },
    ]

    const TILE_PX = 76
    const LABEL_PX = 18
    const TILE_TO_LABEL_GAP_PX = 8
    const GRID_GAP_X_PX = 18
    const GRID_GAP_Y_PX = 22
    const INDICATOR_SPACE_PX = 28
    const BOTTOM_PADDING_PX = 12

    let rootEl: HTMLDivElement
    let cols = $state(5)
    let rows = $state(2)
    let currentPage = $state(0)

    function clamp(value: number, min: number, max: number) {
        return Math.max(min, Math.min(max, value))
    }

    function recalcLayout() {
        if (!rootEl) return

        const rect = rootEl.getBoundingClientRect()
        const width = rect.width
        const availableHeight = Math.max(0, window.innerHeight - rect.top - BOTTOM_PADDING_PX)

        const tileBlockWidth = TILE_PX + GRID_GAP_X_PX
        const nextCols = clamp(Math.floor((width + GRID_GAP_X_PX) / tileBlockWidth), 3, 7)

        const cellHeight = TILE_PX + TILE_TO_LABEL_GAP_PX + LABEL_PX
        const tileBlockHeight = cellHeight + GRID_GAP_Y_PX
        const heightForGrid = Math.max(0, availableHeight - INDICATOR_SPACE_PX)
        const nextRows = clamp(Math.floor((heightForGrid + GRID_GAP_Y_PX) / tileBlockHeight), 1, 5)

        cols = nextCols
        rows = nextRows

        const appsPerPage = Math.max(1, cols * rows)
        const pageCount = Math.max(1, Math.ceil(apps.length / appsPerPage))
        currentPage = clamp(currentPage, 0, pageCount - 1)
    }

    const resizeObserver =
        typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => recalcLayout())

    $effect(() => {
        if (!rootEl) return
        resizeObserver?.observe(rootEl)
        window.addEventListener('resize', recalcLayout, { passive: true })

        // Ensure we measure after layout (especially because this grid is positioned under the input)
        const raf = requestAnimationFrame(recalcLayout)

        return () => {
            cancelAnimationFrame(raf)
            window.removeEventListener('resize', recalcLayout)
            resizeObserver?.unobserve(rootEl)
        }
    })

    onDestroy(() => {
        resizeObserver?.disconnect()
    })

    const pages = $derived.by(() => {
        const appsPerPage = Math.max(1, cols * rows)
        const pageCount = Math.max(1, Math.ceil(apps.length / appsPerPage))

        return Array.from({ length: pageCount }, (_, pageIndex) =>
            apps.slice(pageIndex * appsPerPage, (pageIndex + 1) * appsPerPage)
        )
    })
</script>

<div bind:this={rootEl} class="w-full">
    <div class="relative overflow-hidden">
        <div
            class="flex transition-transform duration-300 ease-out"
            style="transform: translateX(-{currentPage * 100}%);"
        >
            {#each pages as pageApps, pageIndex (pageIndex)}
                <div class="w-full shrink-0">
                    <div
                        class="grid w-full justify-center"
                        style="grid-template-columns: repeat({cols}, {TILE_PX}px); column-gap: {GRID_GAP_X_PX}px; row-gap: {GRID_GAP_Y_PX}px;"
                    >
                        {#each pageApps as app (app.id)}
                            {@const Icon = app.icon}
                            <button
                                type="button"
                                class="group flex flex-col items-center border-none bg-transparent"
                                style="height: {TILE_PX + TILE_TO_LABEL_GAP_PX + LABEL_PX}px;"
                                aria-label={app.title}
                            >
                                <div
                                    class="liquid-glass flex items-center justify-center rounded-3xl shadow-[0_24px_48px_rgba(12,10,30,0.35)] transition-transform duration-150 group-hover:scale-[1.03] group-active:scale-[0.99]"
                                    style="width: {TILE_PX}px; height: {TILE_PX}px; background-color: var(--accent-bg);"
                                >
                                    <span class="liquid-glass__highlight" aria-hidden="true"></span>
                                    <div class="liquid-glass__content">
                                        <Icon className="h-8 w-8 text-white/90" />
                                    </div>
                                </div>
                                <div
                                    class="text-center text-xs font-medium text-white/70"
                                    style="margin-top: {TILE_TO_LABEL_GAP_PX}px; line-height: {LABEL_PX}px; height: {LABEL_PX}px;"
                                >
                                    {app.title}
                                </div>
                            </button>
                        {/each}
                    </div>
                </div>
            {/each}
        </div>
    </div>

    <div class="mt-6 flex items-center justify-center gap-2" aria-label="apps pages">
        {#each pages as _, index (index)}
            <button
                type="button"
                class="transition-all duration-200 {index === currentPage
                    ? 'h-2 w-6 rounded-full bg-white/80'
                    : 'h-2 w-2 rounded-full bg-white/30 hover:bg-white/45'}"
                aria-label={`page ${index + 1}`}
                aria-current={index === currentPage ? 'page' : undefined}
                onclick={() => (currentPage = index)}
            ></button>
        {/each}
    </div>
</div>
