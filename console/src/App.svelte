<script lang="ts">
	import { api } from "$lib/api";
	import { auth } from "$lib/auth.svelte";
	import SplashLoader from "$lib/components/SplashLoader.svelte";
	import { onMount } from "svelte";
	import Dashboard from "./Dashboard.svelte";
	import Login from "./Login.svelte";
	import Welcome from "./Welcome.svelte";

	let isInitialized = $state<boolean | null>(null);
	let showRegister = $state(false);

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

	function handleStart() {
		showRegister = true;
	}
</script>

{#if isInitialized !== null}
	{#if !isInitialized && !showRegister}
		<Welcome onStart={handleStart} />
	{:else if !auth.isAuthenticated}
		<Login onLogin={() => {}} isRegister={showRegister} />
	{:else}
		<Dashboard />
	{/if}
{/if}

<SplashLoader ready={isInitialized !== null} />
