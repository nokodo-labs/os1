import { dev } from '$app/environment'
import { error } from '@sveltejs/kit'

export const ssr = false

export const load = () => {
	if (!dev) throw error(404, 'not found')
}
