<script lang="ts">
    import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
    import BackgroundManager from '$lib/components/backgrounds/BackgroundManager.svelte'
    import DebugMenu from '$lib/components/debug/DebugMenu.svelte'
    import AppSidebar from '$lib/components/sidebar/AppSidebar.svelte'
    import * as Tooltip from '$lib/components/ui/tooltip'
    import { createSidebarContext } from '$lib/contexts/sidebarContext.svelte'
    import { createThemeContext } from '$lib/contexts/themeContext.svelte'
    import '$lib/styles/liquid-glass.css'
    import '../app.css'

    // Initialize sidebar context
    createSidebarContext()
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
            <AppSidebar />

            <!-- Main Content -->
            <div class="relative flex min-w-0 flex-1 flex-col">
                {@render children()}
            </div>
        </div>
    </BackgroundManager>
</Tooltip.Provider>
