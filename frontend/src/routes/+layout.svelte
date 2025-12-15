<script lang="ts">
    import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
    import BackgroundManager from '$lib/components/backgrounds/BackgroundManager.svelte'
    import DebugMenu from '$lib/components/debug/DebugMenu.svelte'
    import ChatSidebar from '$lib/components/sidebar/ChatSidebar.svelte'
    import Dock from '$lib/components/system/Dock.svelte'
    import Island from '$lib/components/system/Island.svelte'
    import * as Tooltip from '$lib/components/ui/tooltip'
    import { createDebugUiContext } from '$lib/contexts/debugUiContext.svelte'
    import { createSidebarContext } from '$lib/contexts/sidebarContext.svelte'
    import { createSystemChromeContext } from '$lib/contexts/systemChromeContext.svelte'
    import { createThemeContext } from '$lib/contexts/themeContext.svelte'
    import '$lib/styles/liquid-glass.css'
    import '../app.css'

    // Initialize sidebar context
    createSidebarContext()
    // Initialize system chrome context
    createSystemChromeContext()
    // DEV ONLY: Debug UI state (persisted locally)
    createDebugUiContext()
    // Initialize theme context
    const theme = createThemeContext()

    // DEV ONLY: Background switcher
    let currentBackground = $state<BackgroundType>('darkveil')
    let { children } = $props()
</script>

<Tooltip.Provider>
    <!-- Background Manager handles all backgrounds with smooth transitions -->
    <BackgroundManager type={currentBackground} config={{ color: '#0a0a0a' }}>
        <!-- DEV ONLY: Debug Menu -->
        <DebugMenu {theme} bind:currentBackground />

        <div class="relative z-1 flex h-screen">
            <!-- Sidebar -->
            <ChatSidebar />

            <!-- Main Content -->
            <div class="relative flex min-w-0 flex-1 flex-col">
                <!-- System chrome: island (top header) -->
                <div class="mx-auto w-full max-w-7xl px-8 pt-8">
                    <Island />
                </div>

                {@render children()}
            </div>

            <!-- System chrome: dock (right sidebar overlay) -->
            <div class="absolute top-0 right-0 bottom-0 z-30 w-80 px-6 pt-8 pb-8">
                <Dock />
            </div>
        </div>
    </BackgroundManager>
</Tooltip.Provider>
