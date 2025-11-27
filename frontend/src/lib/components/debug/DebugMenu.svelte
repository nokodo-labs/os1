<script lang="ts">
    import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
    import {
        accentColors,
        type AccentColor,
        type ThemeMode,
    } from '$lib/contexts/themeContext.svelte'

    interface Props {
        theme: any
        currentBackground: BackgroundType
    }

    let { theme, currentBackground = $bindable() }: Props = $props()

    let showDebugMenu = $state(false)

    const backgrounds: { value: BackgroundType; label: string }[] = [
        { value: 'galaxy', label: 'Galaxy' },
        { value: 'darkveil', label: 'Dark Veil' },
        { value: 'lightbends', label: 'Light Bends' },
        { value: 'lightrays', label: 'Light Rays' },
        { value: 'silk', label: 'Silk' },
        { value: 'static', label: 'Static Color' },
        { value: 'none', label: 'None' },
    ]
</script>

<div class="fixed top-4 right-4 z-50">
    <div class="relative">
        <button
            onclick={() => (showDebugMenu = !showDebugMenu)}
            class="flex items-center gap-2 rounded-lg bg-black/50 px-3 py-2 text-xs text-white/80 backdrop-blur-sm transition-colors hover:bg-black/70 hover:text-white"
        >
            <span>Debug Controls</span>
            <span class="ml-1">▼</span>
        </button>

        {#if showDebugMenu}
            <div
                class="absolute top-full right-0 mt-1 w-56 rounded-lg bg-black/90 p-3 shadow-xl backdrop-blur-sm"
            >
                <!-- Theme Mode -->
                <div class="mb-2 text-[10px] font-bold text-white/40 uppercase">Theme Mode</div>
                <div class="mb-4 flex gap-1">
                    {#each ['light', 'dark', 'system'] as m}
                        <button
                            onclick={() => theme.setMode(m as ThemeMode)}
                            class="flex-1 rounded px-2 py-1.5 text-xs transition-colors {theme.mode ===
                            m
                                ? 'bg-white/20 text-white'
                                : 'text-white/60 hover:bg-white/10 hover:text-white'}"
                        >
                            {m}
                        </button>
                    {/each}
                </div>

                <!-- Accent Color -->
                <div class="mb-2 text-[10px] font-bold text-white/40 uppercase">Accent Color</div>
                <div class="mb-4 grid grid-cols-3 gap-1">
                    {#each Object.keys(accentColors) as color}
                        <button
                            onclick={() => theme.setAccent(color as AccentColor)}
                            class="flex items-center gap-2 rounded px-2 py-1.5 text-xs transition-colors {theme.accent ===
                            color
                                ? 'bg-white/20 text-white'
                                : 'text-white/60 hover:bg-white/10 hover:text-white'}"
                        >
                            <div
                                class="h-2 w-2 rounded-full"
                                style="background-color: {accentColors[color as AccentColor]
                                    .primary}"
                            ></div>
                            {color}
                        </button>
                    {/each}
                </div>

                <!-- Background -->
                <div class="mb-2 text-[10px] font-bold text-white/40 uppercase">Background</div>
                <div class="flex flex-col gap-1">
                    {#each backgrounds as bg}
                        <button
                            onclick={() => {
                                currentBackground = bg.value
                            }}
                            class="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs text-white/80 transition-colors hover:bg-white/10 hover:text-white {currentBackground ===
                            bg.value
                                ? 'bg-white/10 font-medium text-white'
                                : ''}"
                        >
                            {bg.label}
                            {#if currentBackground === bg.value}
                                <div class="h-1.5 w-1.5 rounded-full bg-white"></div>
                            {/if}
                        </button>
                    {/each}
                </div>
            </div>
        {/if}
    </div>
</div>
