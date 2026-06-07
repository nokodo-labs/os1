import { api, unwrap } from '$lib/api'
import type { Agent, Model, Provider, SettingsResponse } from './types'

let _response = $state<SettingsResponse | null>(null)
let _isFetching = $state(true)
let _error = $state<string | null>(null)

let _agents = $state<Agent[]>([])
let _isFetchingAgents = $state(false)
let _agentsError = $state<string | null>(null)

let _models = $state<Model[]>([])
let _isFetchingModels = $state(false)
let _modelsError = $state<string | null>(null)

let _providers = $state<Provider[]>([])

export function getSettingsContext() {
	return {
		get response() {
			return _response
		},
		get isFetching() {
			return _isFetching
		},
		get error() {
			return _error
		},
		get agents() {
			return _agents
		},
		get isFetchingAgents() {
			return _isFetchingAgents
		},
		get agentsError() {
			return _agentsError
		},
		get models() {
			return _models
		},
		get isFetchingModels() {
			return _isFetchingModels
		},
		get modelsError() {
			return _modelsError
		},
		get providers() {
			return _providers
		},
		setFromResponse(r: SettingsResponse) {
			_response = r
		},
		async fetchSettings() {
			_isFetching = true
			_error = null
			try {
				const r = unwrap(await api.GET('/v1/settings'))
				_response = r
				return r
			} catch (e) {
				console.error('Failed to fetch settings', e)
				_error = 'failed to load settings'
			} finally {
				_isFetching = false
			}
		},
		async fetchAgents() {
			_isFetchingAgents = true
			_agentsError = null
			try {
				const list = unwrap(await api.GET('/v1/agents'))
				_agents = [...list].sort((a, b) => a.name.localeCompare(b.name))
			} catch (e) {
				console.error('Failed to fetch agents', e)
				_agentsError = 'failed to load agents'
			} finally {
				_isFetchingAgents = false
			}
		},
		async fetchModels() {
			_isFetchingModels = true
			_modelsError = null
			try {
				const list = unwrap(await api.GET('/v1/models'))
				const label = (m: Model) => m.display_name || m.name || m.id
				_models = [...list].sort((a, b) => label(a).localeCompare(label(b)))
			} catch (e) {
				console.error('Failed to fetch models', e)
				_modelsError = 'failed to load models'
			} finally {
				_isFetchingModels = false
			}
		},
		async fetchProviders() {
			try {
				_providers = unwrap(await api.GET('/v1/providers'))
			} catch (e) {
				console.error('Failed to fetch providers', e)
			}
		},
	}
}

export type SettingsContext = ReturnType<typeof getSettingsContext>
