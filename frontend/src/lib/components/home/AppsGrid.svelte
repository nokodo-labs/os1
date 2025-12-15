<script lang="ts">
    import Bolt from '$lib/components/icons/Bolt.svelte'
    import Bookmark from '$lib/components/icons/Bookmark.svelte'
    import Calendar from '$lib/components/icons/Calendar.svelte'
    import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
    import CheckBox from '$lib/components/icons/CheckBox.svelte'
    import Document from '$lib/components/icons/Document.svelte'

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
    ]
</script>

<div class="w-full">
    <div class="grid grid-cols-3 gap-x-6 gap-y-8 sm:grid-cols-4 md:grid-cols-5">
        {#each apps as app (app.id)}
            {@const Icon = app.icon}
            <button
                type="button"
                class="group flex flex-col items-center gap-2 border-none bg-transparent"
                aria-label={app.title}
            >
                <div
                    class="liquid-glass flex h-20 w-20 items-center justify-center rounded-3xl shadow-[0_24px_48px_rgba(12,10,30,0.35)] transition-transform duration-150 group-hover:scale-[1.03] group-active:scale-[0.99]"
                >
                    <span class="liquid-glass__highlight" aria-hidden="true"></span>
                    <div class="liquid-glass__content">
                        <Icon className="h-9 w-9 text-white/90" />
                    </div>
                </div>
                <div class="text-center text-xs font-medium text-white/70">{app.title}</div>
            </button>
        {/each}
    </div>
</div>
