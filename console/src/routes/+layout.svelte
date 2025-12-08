<script lang="ts">
	import { goto } from "$app/navigation";
	import { page } from "$app/state";
	import { api } from "$lib/api";
	import { auth } from "$lib/auth.svelte";
	import SplashLoader from "$lib/components/SplashLoader.svelte";
	import { onMount } from "svelte";
	import "../app.css";

	let { children } = $props();

	let isInitialized = $state<boolean | null>(null);

	onMount(async () => {
		try {
			const status = await api.getSystemStatus();
			isInitialized = status.initialized;
		} catch (e) {
			console.error("Failed to check system status", e);
			// Fallback to login if check fails
			isInitialized = true;
		}
	});

	$effect(() => {
		if (isInitialized === null) return;

		const path = page.url.pathname;

		if (!isInitialized) {
			if (path !== "/welcome") goto("/welcome");
		} else if (!auth.isAuthenticated) {
			if (path !== "/login" && path !== "/welcome") goto("/login");
		} else {
			// Authenticated
			if (path === "/login" || path === "/welcome" || path === "/")
				goto("/dashboard");
		}
	});
</script>

<SplashLoader ready={isInitialized !== null} />

{#if isInitialized !== null}
	{@render children()}
{/if}
