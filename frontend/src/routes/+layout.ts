// This file is used to configure the static adapter for SPA mode
import { initRuntimeConfig } from '$lib/config/runtime'

import { redirect } from '@sveltejs/kit'

import { getAccessToken } from '$lib/auth/session'

export const ssr = false

const PUBLIC_PATHS = new Set(['/login', '/signup'])

export const load = async ({ url }) => {
	const config = await initRuntimeConfig()

	const token = getAccessToken()
	const isPublic = PUBLIC_PATHS.has(url.pathname)

	if (!token && !isPublic) {
		const next = `${url.pathname}${url.search}`
		throw redirect(307, `/login?next=${encodeURIComponent(next)}`)
	}

	if (token && isPublic) {
		throw redirect(307, url.searchParams.get('next') ?? '/')
	}

	return { config }
}
