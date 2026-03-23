<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { SystemService } from '$lib/api'
	import { auth, markAuthReady } from '$lib/auth.svelte'
	import PendingApproval from '$lib/components/PendingApproval.svelte'
	import SplashLoader from '$lib/components/SplashLoader.svelte'
	import { permissions } from '$lib/stores/permissions.svelte'
	import { onMount } from 'svelte'
	import '../app.css'

	let { children } = $props()

	let isInitialized = $state<boolean | null>(null)
	// false until restoreSession() resolves on mount - prevents premature routing
	let sessionRestored = $state(false)
	let pendingApproval = $state(false)

	onMount(async () => {
		try {
			const status = await SystemService.getSystemStatus()
			isInitialized = status.initialized
		} catch (e) {
			console.error('Failed to check system status', e)
			isInitialized = true
		}

		// Try restoring session from refresh cookie
		if (isInitialized) {
			await auth.restoreSession().catch(() => {})
		}

		sessionRestored = true
		markAuthReady()
	})

	$effect(() => {
		if (!auth.isAuthenticated) {
			pendingApproval = false
			permissions.clear()
			return
		}

		void (async () => {
			await permissions.refresh()
			if (!permissions.hasPermission('console:access')) {
				pendingApproval = true
			} else {
				pendingApproval = false
			}
		})()
	})

	$effect(() => {
		// wait for both system check and session restoration before routing
		if (isInitialized === null || !sessionRestored) return

		const path = page.url.pathname

		if (!isInitialized) {
			if (path !== '/welcome') void goto(resolve('/welcome'))
		} else if (!auth.isAuthenticated) {
			if (path !== '/login' && path !== '/welcome') void goto(resolve('/login'))
		} else {
			// authenticated - only redirect from root/auth pages
			if (path === '/login' || path === '/welcome' || path === '/') {
				void goto(resolve('/dashboard'))
			}
		}
	})
</script>

<SplashLoader ready={isInitialized !== null} />

{#if isInitialized !== null}
	{#if pendingApproval}
		<PendingApproval />
	{:else}
		{@render children()}
	{/if}
{/if}
