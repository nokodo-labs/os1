<script lang="ts">
    import { Cog6, QuestionMarkCircle, SignOut, Sparkles } from '$lib/components/icons'
    import * as Separator from '$lib/components/ui/separator'

    interface UserProfilePanelProps {
        user: {
            name: string
            email: string
            avatar?: string | null
        }
        onClose?: () => void
    }

    let { user, onClose }: UserProfilePanelProps = $props()

    function handleSettingsClick() {
        console.log('Open settings')
        onClose?.()
        // TODO: Navigate to settings page or open settings modal
    }

    function handlePersonalizeClick() {
        console.log('Open personalize')
        onClose?.()
        // TODO: Navigate to personalization page or open modal
    }

    function handleHelpClick() {
        console.log('Open help')
        onClose?.()
        // TODO: Open help modal or navigate to help page
    }

    function handleLogout() {
        console.log('Logout')
        onClose?.()
        // TODO: Implement logout logic
    }

    function getUserInitials(name: string): string {
        return name
            .split(' ')
            .map((n) => n[0])
            .join('')
            .toUpperCase()
            .slice(0, 2)
    }

    interface MenuItem {
        id: string
        icon: any
        label: string
        action: () => void
    }

    const menuItems: MenuItem[] = [
        {
            id: 'settings',
            icon: Cog6,
            label: 'Settings',
            action: handleSettingsClick,
        },
        {
            id: 'personalize',
            icon: Sparkles,
            label: 'Personalize',
            action: handlePersonalizeClick,
        },
        {
            id: 'help',
            icon: QuestionMarkCircle,
            label: 'Help & Support',
            action: handleHelpClick,
        },
    ]
</script>

<div class="w-80 p-4">
    <!-- User Info Section -->
    <div class="flex items-center gap-3 p-3">
        {#if user.avatar}
            <img
                src={user.avatar}
                alt={user.name}
                class="h-10 w-10 shrink-0 rounded-full object-cover"
            />
        {:else}
            <div
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-linear-to-br from-[#8b5cf6] to-[#6366f1] text-sm font-semibold text-white uppercase"
            >
                {getUserInitials(user.name)}
            </div>
        {/if}
        <div class="flex min-w-0 flex-1 flex-col">
            <p
                class="overflow-hidden text-[0.9375rem] font-semibold text-ellipsis whitespace-nowrap text-white"
            >
                {user.name}
            </p>
            <p
                class="overflow-hidden text-[0.8125rem] text-ellipsis whitespace-nowrap text-white/60"
            >
                {user.email}
            </p>
        </div>
    </div>

    <Separator.Root class="my-2 bg-white/10" />

    <!-- Menu Items -->
    <div class="flex flex-col gap-1">
        {#each menuItems as item (item.id)}
            {@const Icon = item.icon}
            <button
                class="flex w-full items-center gap-3 rounded-lg border border-transparent bg-transparent px-4 py-3 text-left text-sm font-medium text-white transition-all duration-150 hover:border-white/20 hover:bg-white/10 active:scale-[0.98]"
                onclick={item.action}
            >
                <Icon className="h-4.5 w-4.5 shrink-0" />
                <span>{item.label}</span>
            </button>
        {/each}
    </div>

    <Separator.Root class="my-2 bg-white/10" />

    <!-- Logout Button -->
    <button
        class="flex w-full items-center gap-3 rounded-lg border border-transparent bg-transparent px-4 py-3 text-left text-sm font-medium text-[rgb(239,68,68)] transition-all duration-150 hover:border-[rgba(239,68,68,0.3)] hover:bg-[rgba(239,68,68,0.15)] active:scale-[0.98]"
        onclick={handleLogout}
    >
        <SignOut className="h-4.5 w-4.5 shrink-0" />
        <span>Log out</span>
    </button>
</div>
