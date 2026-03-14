<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { api } from '$lib/api/client'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { settingsState } from '$lib/stores/settings.svelte'

	let identifier = $state('')
	let password = $state('')
	let isSubmitting = $state(false)
	let errorMessage = $state<string | null>(null)

	// NOTE: searchParams access must be guarded for SSG/prerender compatibility
	const next = $derived(
		browser
			? typeof page.state.next === 'string'
				? page.state.next
				: (page.url.searchParams.get('next') ?? '/')
			: '/'
	)

	pageTitleStore.pageTitle = 'login'

	const allowSignups = $derived(settingsState.data?.security?.allow_signups ?? true)
	const oidcOnly = $derived(settingsState.data?.security?.oidc?.only ?? false)

	$effect(() => {
		if (!browser) return
		const fromState = page.state.email
		if (fromState && !identifier) identifier = fromState
		const fromQuery = page.url.searchParams.get('email')
		if (fromQuery && !identifier) identifier = fromQuery
	})

	function nextTargetFromNextValue(
		nextValue: string
	): { type: 'home' } | { type: 'chat'; id: string } {
		if (nextValue.startsWith('/c/')) {
			const id = nextValue.slice(3).split(/[/?#]/)[0]
			if (id) return { type: 'chat', id }
		}
		return { type: 'home' }
	}

	async function onSubmit(event: SubmitEvent) {
		event.preventDefault()
		if (isSubmitting) return
		if (oidcOnly) return

		errorMessage = null
		isSubmitting = true

		try {
			const { data, error, response } = await api.POST(
				'/v1/auth/login/access-token',
				{
					headers: {
						'Content-Type': 'application/x-www-form-urlencoded',
					},
					body: {
						username: identifier.trim(),
						password,
						scope: '',
					},
				}
			)

			if (error || !data) {
				const detail = (error as { detail?: unknown } | undefined)?.detail
				if (typeof detail === 'string' && detail) throw new Error(detail)
				if (Array.isArray(detail) && detail.length) {
					const messages = detail
						.map((item) =>
							typeof item === 'object' && item && 'msg' in item
								? (item as { msg: string }).msg
								: null
						)
						.filter((msg): msg is string => Boolean(msg))
					if (messages.length) throw new Error(messages.join(', '))
				}
				throw new Error(response.statusText || 'failed to sign in')
			}

			session.setToken(data.access_token)
			void session.refresh()
			const target = nextTargetFromNextValue(next)
			if (target.type === 'chat') {
				await goto(resolve('/c/[id]', { id: target.id }))
			} else {
				await goto(resolve('/'))
			}
		} catch (err) {
			errorMessage = err instanceof Error ? err.message : 'failed to sign in'
		} finally {
			isSubmitting = false
		}
	}
</script>

<div class="flex-1 overflow-y-auto">
	<div class="mx-auto flex min-h-full w-full max-w-7xl flex-col px-8 pt-8 pb-24">
		<div class="flex flex-1 items-center justify-center">
			<div class="w-full max-w-md">
				<div
					class="liquid-glass liquid-glass--frosted rounded-container overflow-hidden shadow-[0_28px_80px_rgba(0,0,0,0.45)]"
				>
					<div class="p-8">
						<div class="mb-8 space-y-2">
							<h1 class="text-foreground text-2xl font-medium">welcome back</h1>
							<p class="text-foreground/55 text-sm">sign in to continue</p>
						</div>

						<form class="space-y-4" onsubmit={onSubmit}>
							<div class="space-y-2">
								<label
									class="text-foreground/75 text-sm font-medium"
									for="identifier">email or username</label
								>
								<input
									id="identifier"
									type="text"
									autocomplete="username"
									required
									bind:value={identifier}
									placeholder="email or username"
									class="border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/35 focus:border-foreground/20 w-full rounded-full border px-4 py-3 text-sm transition-colors outline-none"
								/>
							</div>

							<div class="space-y-2">
								<label class="text-foreground/75 text-sm font-medium" for="password"
									>password</label
								>
								<input
									id="password"
									type="password"
									autocomplete="current-password"
									required
									bind:value={password}
									placeholder="••••••••"
									class="border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/35 focus:border-foreground/20 w-full rounded-full border px-4 py-3 text-sm transition-colors outline-none"
								/>
							</div>

							{#if oidcOnly}
								<div
									class="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200"
									role="alert"
								>
									password login is disabled. sign in with oidc.
								</div>
							{:else if errorMessage}
								<div
									class="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200"
									role="alert"
								>
									{errorMessage}
								</div>
							{/if}

							<button
								type="submit"
								disabled={isSubmitting || oidcOnly}
								class="interactive bg-foreground text-background hover:bg-foreground/90 focus-visible:ring-foreground/20 inline-flex h-11 w-full items-center justify-center rounded-full font-medium transition-all focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100"
							>
								{#if isSubmitting}
									<ShimmerText
										className="inline-block"
										textColor="var(--background)"
										waveColor="color-mix(in oklch, var(--background) 35%, transparent)"
									>
										signing in
									</ShimmerText>
								{:else}
									sign in
								{/if}
							</button>
						</form>

						{#if allowSignups}
							<div class="text-foreground/55 mt-6 text-center text-sm">
								don't have an account?
								<a
									href={resolve('/signup')}
									class="text-foreground/80 hover:text-foreground ml-1 font-medium"
								>
									sign up
								</a>
							</div>
						{/if}
					</div>
				</div>
			</div>
		</div>
	</div>
</div>
