<script lang="ts">
	import RolePicker from '$lib/components/RolePicker.svelte'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Switch } from '$lib/components/ui/switch'
	import { Lock } from '@lucide/svelte'

	type Props = {
		accessTokenExpireMinutes?: string
		refreshTokenExpireDays?: string
		authCookieSecure?: boolean
		sessionTimeoutMinutes?: string
		requireEmailVerification?: boolean
		allowedEmailDomains?: string
		allowSignups?: boolean
		autoSignupRoleIds?: string[]
		oidcEnabled?: boolean
		oidcIssuerUrl?: string
		oidcClientId?: string
		oidcClientSecret?: string
		oidcRedirectUri?: string
		oidcScopes?: string
		oidcOnly?: boolean
		// read-only (write-locked)
		secretKeyConfigured?: boolean
		jwtAlgorithm?: string
		enableOauth?: boolean
		corsOrigins?: string
	}

	let {
		accessTokenExpireMinutes = $bindable(''),
		refreshTokenExpireDays = $bindable(''),
		authCookieSecure = $bindable(false),
		sessionTimeoutMinutes = $bindable(''),
		requireEmailVerification = $bindable(false),
		allowedEmailDomains = $bindable(''),
		allowSignups = $bindable(true),
		autoSignupRoleIds = $bindable([]),
		oidcEnabled = $bindable(false),
		oidcIssuerUrl = $bindable(''),
		oidcClientId = $bindable(''),
		oidcClientSecret = $bindable(''),
		oidcRedirectUri = $bindable(''),
		oidcScopes = $bindable(''),
		oidcOnly = $bindable(false),
		secretKeyConfigured = false,
		jwtAlgorithm = '',
		enableOauth = false,
		corsOrigins = '',
	}: Props = $props()
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>security</CardTitle>
		<CardDescription>authentication and session behavior.</CardDescription>
	</CardHeader>
	<CardContent class="space-y-5">
		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<div class="flex items-center justify-between gap-2">
					<Label for="secret_key">secret key</Label>
					<span
						class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
					>
						<Lock class="h-3 w-3" />
						env-only
					</span>
				</div>
				<Input
					id="secret_key"
					value={secretKeyConfigured ? '(configured)' : '(not set)'}
					disabled
					class="rounded-xl"
				/>
				<p class="text-xs text-zinc-500">set via environment variables only.</p>
			</div>
			<div class="space-y-2">
				<div class="flex items-center justify-between gap-2">
					<Label for="jwt_algorithm">jwt algorithm</Label>
					<span
						class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
					>
						<Lock class="h-3 w-3" />
						env-only
					</span>
				</div>
				<Input
					id="jwt_algorithm"
					value={jwtAlgorithm || '(not set)'}
					disabled
					class="rounded-xl"
				/>
				<p class="text-xs text-zinc-500">set via environment variables only.</p>
			</div>
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<div class="flex items-center justify-between gap-2">
					<Label for="enable_oauth">enable oauth</Label>
					<span
						class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
					>
						<Lock class="h-3 w-3" />
						env-only
					</span>
				</div>
				<Input
					id="enable_oauth"
					value={enableOauth ? 'true' : 'false'}
					disabled
					class="rounded-xl"
				/>
				<p class="text-xs text-zinc-500">set via environment variables only.</p>
			</div>
			<div class="space-y-2">
				<div class="flex items-center justify-between gap-2">
					<Label for="cors_origins">cors origins</Label>
					<span
						class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
					>
						<Lock class="h-3 w-3" />
						env-only
					</span>
				</div>
				<Input
					id="cors_origins"
					value={corsOrigins || '(not set)'}
					disabled
					class="rounded-xl"
				/>
				<p class="text-xs text-zinc-500">set via environment variables only.</p>
			</div>
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<Label for="access_expire">access token expire minutes</Label>
				<p class="text-xs text-zinc-500">
					how long access tokens remain valid before the client must refresh.
				</p>
				<Input
					id="access_expire"
					type="number"
					bind:value={accessTokenExpireMinutes}
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<Label for="refresh_expire">refresh token expire days</Label>
				<p class="text-xs text-zinc-500">
					how long refresh tokens remain valid; controls maximum session length.
				</p>
				<Input
					id="refresh_expire"
					type="number"
					bind:value={refreshTokenExpireDays}
					class="rounded-xl"
				/>
			</div>
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<Label for="session_timeout">session timeout minutes</Label>
				<p class="text-xs text-zinc-500">
					idle timeout after which the user is automatically logged out.
				</p>
				<Input
					id="session_timeout"
					type="number"
					bind:value={sessionTimeoutMinutes}
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<Label for="allowed_domains">allowed email domains</Label>
				<Input
					id="allowed_domains"
					bind:value={allowedEmailDomains}
					placeholder="example.com, example.org"
					class="rounded-xl"
				/>
				<p class="text-xs text-zinc-500">
					only emails from these domains can register. leave empty to allow all.
				</p>
			</div>
		</div>

		<div class="flex items-center justify-between">
			<div class="space-y-0.5">
				<Label for="allow_signups">allow new user signups</Label>
				<p class="text-xs text-zinc-500">
					when off, admins or users with users:manage only.
				</p>
			</div>
			<Switch
				id="allow_signups"
				checked={allowSignups}
				onCheckedChange={(v: boolean) => (allowSignups = v)}
			/>
		</div>

		<div class="space-y-2">
			<Label>auto-apply roles</Label>
			<RolePicker bind:value={autoSignupRoleIds} />
			<p class="text-xs text-zinc-500">
				roles automatically assigned to new users on signup.
			</p>
		</div>

		<div class="flex items-center justify-between">
			<div class="space-y-0.5">
				<Label for="cookie_secure">auth cookie secure</Label>
				<p class="text-xs text-zinc-500">recommended true in production.</p>
			</div>
			<Switch
				id="cookie_secure"
				checked={authCookieSecure}
				onCheckedChange={(v: boolean) => (authCookieSecure = v)}
			/>
		</div>

		<div class="flex items-center justify-between">
			<div class="space-y-0.5">
				<Label for="email_verification">require email verification</Label>
				<p class="text-xs text-zinc-500">
					require users to verify their email address before accessing the app.
				</p>
			</div>
			<Switch
				id="email_verification"
				checked={requireEmailVerification}
				onCheckedChange={(v: boolean) => (requireEmailVerification = v)}
			/>
		</div>

		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<p class="mb-1 text-sm font-medium">oidc</p>
			<p class="mb-4 text-xs text-zinc-500">
				openid connect provider settings for single sign-on.
			</p>

			<div class="mb-4 flex items-center justify-between">
				<div class="space-y-0.5">
					<Label for="oidc_enabled">enable oidc</Label>
					<p class="text-xs text-zinc-500">
						allow users to sign in with an oidc provider.
					</p>
				</div>
				<Switch
					id="oidc_enabled"
					checked={oidcEnabled}
					onCheckedChange={(v: boolean) => (oidcEnabled = v)}
				/>
			</div>

			{#if oidcEnabled}
				<div class="grid gap-4 md:grid-cols-2">
					<div class="space-y-2">
						<Label for="oidc_issuer">issuer url</Label>
						<Input
							id="oidc_issuer"
							bind:value={oidcIssuerUrl}
							placeholder="https://issuer.example.com"
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="oidc_client_id">client id</Label>
						<Input id="oidc_client_id" bind:value={oidcClientId} class="rounded-xl" />
					</div>
					<div class="space-y-2">
						<Label for="oidc_client_secret">client secret</Label>
						<Input
							id="oidc_client_secret"
							type="password"
							bind:value={oidcClientSecret}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="oidc_redirect">redirect uri</Label>
						<Input
							id="oidc_redirect"
							bind:value={oidcRedirectUri}
							placeholder="https://app.example.com/oidc/callback"
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2 md:col-span-2">
						<Label for="oidc_scopes">scopes</Label>
						<Input
							id="oidc_scopes"
							bind:value={oidcScopes}
							placeholder="openid, profile, email"
							class="rounded-xl"
						/>
						<p class="text-xs text-zinc-500">comma-separated list.</p>
					</div>
				</div>

				<div class="mt-4 flex items-center justify-between">
					<div class="space-y-0.5">
						<Label for="oidc_only">oidc only</Label>
						<p class="text-xs text-zinc-500">
							disable password login. requires oidc to be enabled &amp; configured.
						</p>
					</div>
					<Switch
						id="oidc_only"
						checked={oidcOnly}
						onCheckedChange={(v: boolean) => (oidcOnly = v)}
					/>
				</div>
			{/if}
		</div>
	</CardContent>
</Card>
