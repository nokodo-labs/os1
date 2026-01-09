import {
	AgentsService,
	AuthService,
	MemoriesService,
	ModelsService,
	OpenAPI,
	PluginsService,
	ProjectsService,
	PromptsService,
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
	MemoriesService,
	ModelsService,
	PluginsService,
	ProjectsService,
	PromptsService,
	ProvidersService,
	SystemService,
	ThreadsService,
	UsersService,
}

export type {
	AccessControlEntry,
	AccessControlEntryCreate,
	AccessRole,
	Agent,
	AgentCreate,
	AgentUpdate,
	AgentVisibility,
	Memory,
	MemoryCreate,
	Message,
	MessageCreate,
	Model,
	ModelCreate,
	ModelType,
	ModelUpdate,
	Plugin,
	PluginCreate,
	PluginInfo,
	PluginType,
	PluginUpdate,
	Project,
	Prompt,
	PromptCreate,
	PromptUpdate,
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
