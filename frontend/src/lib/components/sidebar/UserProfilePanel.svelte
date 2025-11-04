<script lang="ts">
    import { Cog6, QuestionMarkCircle, SignOut, Sparkles } from '$lib/components/icons'
    import * as Separator from '$lib/components/ui/separator'
    import '$lib/styles/user-profile.css'

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

<div class="user-profile-panel">
    <!-- User Info Section -->
    <div class="user-profile-header">
        {#if user.avatar}
            <img src={user.avatar} alt={user.name} class="user-avatar" />
        {:else}
            <div class="user-avatar-initials">
                {getUserInitials(user.name)}
            </div>
        {/if}
        <div class="user-info">
            <p class="user-name">{user.name}</p>
            <p class="user-email">{user.email}</p>
        </div>
    </div>

    <Separator.Root class="my-2 bg-white/10" />

    <!-- Menu Items -->
    <div class="menu-section">
        {#each menuItems as item (item.id)}
            {@const Icon = item.icon}
            <button class="menu-item" onclick={item.action}>
                <Icon className="h-4.5 w-4.5 shrink-0" />
                <span class="menu-item-label">{item.label}</span>
            </button>
        {/each}
    </div>

    <Separator.Root class="my-2 bg-white/10" />

    <!-- Logout Button -->
    <div class="logout-section">
        <button class="logout-button" onclick={handleLogout}>
            <SignOut className="h-4.5 w-4.5 shrink-0" />
            <span class="menu-item-label">Log out</span>
        </button>
    </div>
</div>
