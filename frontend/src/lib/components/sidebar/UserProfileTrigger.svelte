<script lang="ts">
    import '$lib/styles/liquid-glass.css'
    import { onMount } from 'svelte'
    import UserProfilePanel from './UserProfilePanel.svelte'

    interface UserProfileTriggerProps {
        user: {
            name: string
            email: string
            avatar?: string | null
        }
        isExpanded?: boolean
    }

    let { user, isExpanded = false }: UserProfileTriggerProps = $props()

    let isOpen = $state(false)
    let buttonElement: HTMLButtonElement | undefined = $state()
    let panelElement: HTMLDivElement | undefined = $state()

    function getUserInitials(name: string): string {
        return name
            .split(' ')
            .map((n) => n[0])
            .join('')
            .toUpperCase()
            .slice(0, 2)
    }

    function togglePanel() {
        isOpen = !isOpen
    }

    function closePanel() {
        isOpen = false
    }

    function handleClickOutside(event: MouseEvent) {
        if (
            isOpen &&
            panelElement &&
            buttonElement &&
            !panelElement.contains(event.target as Node) &&
            !buttonElement.contains(event.target as Node)
        ) {
            closePanel()
        }
    }

    onMount(() => {
        document.addEventListener('click', handleClickOutside)
        return () => {
            document.removeEventListener('click', handleClickOutside)
        }
    })
</script>

<div class="user-profile-trigger-container mt-auto">
    <button
        bind:this={buttonElement}
        class="relative flex items-center border border-transparent bg-transparent {isExpanded
            ? 'w-full justify-start gap-3 p-3'
            : 'h-14 w-14 justify-center p-3'} cursor-pointer rounded-xl text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5"
        onclick={togglePanel}
        aria-label="User Profile"
        aria-expanded={isOpen}
    >
        {#if user.avatar}
            <img
                src={user.avatar}
                alt={user.name}
                class="{isExpanded
                    ? 'h-10 w-10'
                    : 'h-9 w-9'} shrink-0 rounded-full transition-all duration-200"
            />
        {:else}
            <div
                class="{isExpanded
                    ? 'h-10 w-10 text-[0.875rem]'
                    : 'h-9 w-9 text-[0.75rem]'} flex shrink-0 items-center justify-center rounded-full font-semibold text-white uppercase transition-all duration-200"
                style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-secondary));"
            >
                {getUserInitials(user.name)}
            </div>
        {/if}
        {#if isExpanded}
            <div
                class="flex min-w-0 flex-col text-left opacity-0 transition-opacity delay-100 duration-300 {isExpanded
                    ? 'opacity-100'
                    : ''}"
            >
                <p
                    class="overflow-hidden text-sm font-semibold text-ellipsis whitespace-nowrap text-white"
                >
                    {user.name}
                </p>
                <p class="overflow-hidden text-xs text-ellipsis whitespace-nowrap text-white/60">
                    {user.email}
                </p>
            </div>
        {/if}
    </button>

    {#if isOpen}
        <div bind:this={panelElement} class="profile-panel-wrapper liquid-glass">
            <div class="liquid-glass__highlight"></div>
            <div class="liquid-glass__content">
                <UserProfilePanel {user} onClose={closePanel} />
            </div>
        </div>
    {/if}
</div>

<style>
    .user-profile-trigger-container {
        position: relative;
    }

    .profile-panel-wrapper {
        position: absolute;
        bottom: 0;
        left: calc(100% + 0.5rem);
        z-index: 50;
        border-radius: 0.75rem;
        animation: fadeIn 0.15s ease-out;
    }

    :global(.dark) .profile-panel-wrapper {
        border-color: rgba(255, 255, 255, 0.1);
    }

    @keyframes fadeIn {
        from {
            opacity: 0;
            transform: translateY(4px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
</style>
