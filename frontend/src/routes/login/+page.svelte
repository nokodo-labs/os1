<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { v1Client } from '$lib/api/v1/client'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { session } from '$lib/stores/session.svelte'

	let email = $state('')
	let password = $state('')
	let isSubmitting = $state(false)
	let errorMessage = $state<string | null>(null)

	// NOTE: searchParams access must be guarded for SSG/prerender compatibility
	const next = $derived(browser ? (page.url.searchParams.get('next') ?? '/') : '/')

	pageTitleStore.pageTitle = 'login'

	$effect(() => {
		if (!browser) return
		const fromQuery = page.url.searchParams.get('email')
		if (fromQuery && !email) email = fromQuery
	})

	async function onSubmit(event: SubmitEvent) {
		event.preventDefault()
		if (isSubmitting) return

		errorMessage = null
		isSubmitting = true

		try {
			const { data, error, response } = await v1Client().POST('/auth/login/access-token', {
				headers: {
					'Content-Type': 'application/x-www-form-urlencoded',
				},
				body: {
					username: email.trim(),
					password,
					scope: '',
				},
			})

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
			// @ts-expect-error resolve typing is narrower than our constructed URL
			await goto(resolve(next as never))
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
							<h1 class="text-2xl font-medium text-white">welcome back</h1>
							<p class="text-sm text-white/55">sign in to continue</p>
						</div>

						<form class="space-y-4" onsubmit={onSubmit}>
							<div class="space-y-2">
								<label class="text-sm font-medium text-white/75" for="email"
									>email</label
								>
								<input
									id="email"
									type="email"
									autocomplete="email"
									required
									bind:value={email}
									placeholder="you@nokodo.net"
									class="w-full rounded-full border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 transition-colors outline-none placeholder:text-white/35 focus:border-white/20"
								/>
							</div>

							<div class="space-y-2">
								<label class="text-sm font-medium text-white/75" for="password"
									>password</label
								>
								<input
									id="password"
									type="password"
									autocomplete="current-password"
									required
									bind:value={password}
									placeholder="••••••••"
									class="w-full rounded-full border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 transition-colors outline-none placeholder:text-white/35 focus:border-white/20"
								/>
							</div>

							{#if errorMessage}
								<div
									class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/75"
								>
									{errorMessage}
								</div>
							{/if}

							<button
								type="submit"
								disabled={isSubmitting}
								class="h-11 w-full rounded-full bg-white font-medium text-black transition-all hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-50"
							>
								{isSubmitting ? 'signing in…' : 'sign in'}
							</button>
						</form>

						<div class="mt-6 text-center text-sm text-white/55">
							don't have an account?
							<a
								href={resolve('/signup')}
								class="ml-1 font-medium text-white/80 hover:text-white"
							>
								sign up
							</a>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</div>
