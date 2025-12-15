import {
	AgentsService,
	AuthService,
	ModelsService,
	OpenAPI,
	ProvidersService,
	SystemService,
	ThreadsService,
	UsersService,
} from './generated'

const DEFAULT_API_BASE = 'http://localhost:8000/v1'

OpenAPI.BASE = import.meta.env.VITE_API_URL || DEFAULT_API_BASE
OpenAPI.TOKEN = async () => {
	if (typeof localStorage === 'undefined') return ''
	return localStorage.getItem('access_token') ?? ''
}

export { ApiError } from './generated'
export {
	AgentsService,
	AuthService,
	ModelsService,
	ProvidersService,
	SystemService,
	ThreadsService,
	UsersService,
}

export type {
	Agent,
	AgentCreate,
	AgentVisibility,
	Message,
	MessageCreate,
	Model,
	ModelCreate,
	ModelType,
	ModelUpdate,
	Provider,
	ProviderCreate,
	ProviderStatus,
	ProviderType,
	ProviderUpdate,
	Thread,
	ThreadCreate,
	Token,
	User,
	UserCreate,
} from './generated'
