<script lang="ts">
    import { api } from './lib/api'

    let health = $state<{ status: string } | null>(null)
    const IS_PAGES = typeof import.meta !== 'undefined' && import.meta.env?.VITE_PAGES === 'true'

    async function checkHealth() {
        try {
            health = await api.healthCheck()
            console.log('Health check success:', health)
        } catch (error) {
            console.error('Health check failed, retrying in 2s:', error)
            setTimeout(checkHealth, 2000)
        }
    }

    $effect(() => {
        if (IS_PAGES) {
            // On static Pages we don't have a backend; mark as healthy/demo
            health = { status: 'pages' }
            return
        }
        console.log('Starting health checks...')
        checkHealth()
    })

    async function copyToClipboard(text: string, target: EventTarget | null) {
        if (!target || !(target instanceof HTMLButtonElement)) return
        const button = target
        await navigator.clipboard.writeText(text)
        const original = button.textContent
        button.textContent = '✓'
        button.classList.add('!text-green-400')
        setTimeout(() => {
            button.textContent = original
            button.classList.remove('!text-green-400')
        }, 1500)
    }
</script>

<svelte:head>
    <style>
        @keyframes float {
            0%,
            100% {
                transform: translate(0, 0) rotate(0deg);
            }
            33% {
                transform: translate(30px, -30px) rotate(5deg);
            }
            66% {
                transform: translate(-20px, 20px) rotate(-3deg);
            }
        }
        @keyframes float-slow {
            0%,
            100% {
                transform: translate(0, 0) scale(1);
            }
            50% {
                transform: translate(-40px, -40px) scale(1.1);
            }
        }
        @keyframes pulse-glow {
            0%,
            100% {
                opacity: 0.4;
                box-shadow: 0 0 20px rgba(59, 130, 246, 0.3);
            }
            50% {
                opacity: 0.8;
                box-shadow: 0 0 40px rgba(59, 130, 246, 0.5);
            }
        }
        @keyframes gradient-shift {
            0%,
            100% {
                background-position: 0% 50%;
            }
            50% {
                background-position: 100% 50%;
            }
        }
        @keyframes morph {
            0%,
            100% {
                border-radius: 60% 40% 30% 70% / 60% 30% 70% 40%;
            }
            50% {
                border-radius: 30% 60% 70% 40% / 50% 60% 30% 60%;
            }
        }
        .morphing-blob {
            animation:
                float 25s ease-in-out infinite,
                morph 20s ease-in-out infinite;
        }
        @keyframes fade-in-up {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        .float-shape-1 {
            animation: float 20s ease-in-out infinite;
        }
        .float-shape-2 {
            animation: float-slow 25s ease-in-out infinite;
        }
        .float-shape-3 {
            animation: float 30s ease-in-out infinite;
        }
        .gradient-text {
            background: linear-gradient(135deg, #3b82f6, #8b5cf6, #ec4899, #3b82f6);
            background-size: 300% 300%;
            animation: gradient-shift 8s ease infinite;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .fade-in-up {
            animation: fade-in-up 0.8s ease-out forwards;
        }
        .grid-pattern {
            background-image:
                linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
            background-size: 50px 50px;
        }
    </style>
</svelte:head>

<main class="relative min-h-screen overflow-hidden bg-black text-white">
    <!-- Grid pattern overlay -->
    <div class="grid-pattern pointer-events-none fixed inset-0 opacity-30"></div>

    <!-- Animated gradient orbs with morphing -->
    <div class="pointer-events-none fixed inset-0">
        <div
            class="morphing-blob absolute -top-40 -left-40 h-[350px] w-[350px] bg-blue-500/12 blur-3xl"
            style="animation-delay: 0s;"
        ></div>
        <div
            class="morphing-blob absolute top-1/3 -right-60 h-[450px] w-[450px] bg-purple-500/10 blur-3xl"
            style="animation-delay: 3s;"
        ></div>
        <div
            class="morphing-blob absolute -bottom-40 left-1/4 h-[300px] w-[300px] bg-pink-500/8 blur-3xl"
            style="animation-delay: 6s;"
        ></div>
        <div
            class="morphing-blob absolute top-2/3 right-1/3 h-[280px] w-[280px] bg-cyan-400/10 blur-3xl"
            style="animation-delay: 9s;"
        ></div>
    </div>

    <!-- Content -->
    <div class="relative z-10">
        <!-- Header -->
        <header class="border-b border-zinc-800/50 bg-black/40 backdrop-blur-md">
            <div class="flex w-full items-center justify-between px-5 py-4">
                <div class="flex items-center gap-4">
                    <a href="https://nokodo.net" target="_blank" rel="noopener noreferrer">
                        <img
                            src="https://nokodo.net/media/images/logo_full.svg"
                            alt="nokodo"
                            class="h-5 transition-all duration-300 hover:scale-105 sm:h-6"
                        />
                    </a>
                </div>
                <div class="flex items-center gap-2">
                    {#if health}
                        <div
                            class="group relative flex items-center gap-2 rounded-full bg-green-500/10 px-2.5 py-1.5 text-xs font-medium text-green-400 ring-1 ring-green-500/30 backdrop-blur-sm transition-all hover:ring-green-500/50 sm:text-sm"
                            title={IS_PAGES
                                ? 'Static preview (no backend polling)'
                                : 'API server is running and healthy'}
                        >
                            <div
                                class="h-1.5 w-1.5 animate-pulse rounded-full bg-green-500 shadow-lg shadow-green-500/50 sm:h-2 sm:w-2"
                            ></div>
                            <span class="lowercase">{IS_PAGES ? 'preview' : 'online'}</span>
                            <div
                                class="pointer-events-none absolute right-0 -bottom-12 z-50 hidden w-48 rounded-lg bg-zinc-900 px-3 py-2 text-xs font-normal text-zinc-300 opacity-0 shadow-xl ring-1 ring-zinc-700 transition-opacity group-hover:block group-hover:opacity-100"
                            >
                                {IS_PAGES ? 'Static site preview' : 'API health check passed'}
                            </div>
                        </div>
                    {:else}
                        <div
                            class="group relative flex items-center gap-2 rounded-full bg-blue-500/5 px-2.5 py-1.5 text-xs font-medium text-blue-400 ring-1 ring-blue-500/20 backdrop-blur-sm sm:text-sm"
                            title="Connecting to API server..."
                        >
                            <div
                                class="h-1.5 w-1.5 rounded-full bg-blue-500 sm:h-2 sm:w-2"
                                style="animation: pulse-glow 2s ease-in-out infinite;"
                            ></div>
                            <span class="lowercase">starting...</span>
                            <div
                                class="pointer-events-none absolute right-0 -bottom-12 z-50 hidden w-48 rounded-lg bg-zinc-900 px-3 py-2 text-xs font-normal text-zinc-300 opacity-0 shadow-xl ring-1 ring-zinc-700 transition-opacity group-hover:block group-hover:opacity-100"
                            >
                                waiting for API connection
                            </div>
                        </div>
                    {/if}
                </div>
            </div>
        </header>

        <!-- Hero -->
        <section
            class="flex min-h-[calc(100vh-200px)] w-full flex-col items-center justify-center px-5 py-16 text-center sm:py-24 lg:py-32"
        >
            <div
                class="fade-in-up mb-8 inline-flex items-center gap-2 rounded-full bg-zinc-900/80 px-3 py-1.5 text-xs font-medium text-zinc-300 ring-1 ring-zinc-800/50 backdrop-blur-sm transition-all duration-300 hover:bg-zinc-900 hover:ring-blue-500/30 sm:mb-10 sm:px-4 sm:py-2 sm:text-sm"
                style="animation-delay: 0.1s;"
            >
                <span class="text-base sm:text-lg">🚀</span>
                <span class="lowercase">production-ready monorepo</span>
            </div>

            <h1
                class="fade-in-up mb-6 max-w-5xl text-4xl leading-[1.1] font-bold tracking-tight sm:text-5xl md:text-6xl lg:text-7xl"
                style="animation-delay: 0.2s;"
            >
                <span class="lowercase">build</span>
                <span class="gradient-text font-extrabold">full-stack apps</span>
                <span class="lowercase">fast</span>
            </h1>

            <p
                class="fade-in-up mb-12 max-w-2xl px-4 text-base text-zinc-400 lowercase sm:mb-16 sm:text-lg lg:text-xl"
                style="animation-delay: 0.3s;"
            >
                FastAPI + Svelte 5 + TypeScript + PostgreSQL + Docker.<br />
                <span class="text-zinc-500">type-safe API client. async-first. ready to scale.</span
                >
            </p>

            <!-- Quick Start -->
            <div
                class="fade-in-up w-full max-w-4xl rounded-2xl bg-zinc-900/50 p-5 shadow-2xl ring-1 shadow-black/50 ring-zinc-800/50 backdrop-blur-md transition-all duration-500 hover:bg-zinc-900/60 hover:ring-zinc-700 sm:p-5"
                style="animation-delay: 0.4s;"
            >
                <h2
                    class="mb-6 bg-linear-to-r from-white to-zinc-400 bg-clip-text text-xl font-semibold text-transparent lowercase sm:mb-8 sm:text-2xl"
                >
                    quick start
                </h2>

                <div class="space-y-5 sm:space-y-6">
                    <div class="group">
                        <div
                            class="mb-2.5 flex items-center gap-2.5 text-sm font-semibold text-zinc-300 lowercase sm:mb-3 sm:gap-3 sm:text-base"
                        >
                            <span
                                class="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/10 text-xs font-bold text-blue-400 ring-1 ring-blue-500/30 backdrop-blur-sm transition-all duration-300 group-hover:scale-110 group-hover:bg-blue-500/20 group-hover:ring-blue-500/50 sm:h-8 sm:w-8 sm:text-sm"
                                >1</span
                            >
                            clone & setup
                        </div>
                        <div class="relative ml-0 sm:ml-11">
                            <div
                                class="overflow-x-auto rounded-lg bg-black/80 p-3 pr-16 font-mono text-xs text-zinc-300 ring-1 ring-zinc-800/50 transition-all duration-300 group-hover:ring-zinc-700 sm:p-4 sm:text-sm"
                            >
                                <button
                                    onclick={(e) =>
                                        copyToClipboard(
                                            'git clone https://github.com/nokodo-labs/monorepo-template.git\ncd monorepo-template/.docker && docker compose up -d',
                                            e.currentTarget
                                        )}
                                    class="absolute top-3 right-3 z-10 rounded border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-xs font-medium text-zinc-400 shadow-lg transition-all hover:border-zinc-600 hover:bg-zinc-700 hover:text-white"
                                    >copy</button
                                >
                                <div class="whitespace-nowrap">
                                    git clone https://github.com/nokodo-labs/monorepo-template.git
                                </div>
                                <div class="mt-1 whitespace-nowrap">
                                    cd monorepo-template/.docker && docker compose up -d
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="group">
                        <div
                            class="mb-2.5 flex items-center gap-2.5 text-sm font-semibold text-zinc-300 lowercase sm:mb-3 sm:gap-3 sm:text-base"
                        >
                            <span
                                class="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-500/10 text-xs font-bold text-purple-400 ring-1 ring-purple-500/30 backdrop-blur-sm transition-all duration-300 group-hover:scale-110 group-hover:bg-purple-500/20 group-hover:ring-purple-500/50 sm:h-8 sm:w-8 sm:text-sm"
                                >2</span
                            >
                            install dependencies
                        </div>
                        <div class="relative ml-0 sm:ml-11">
                            <div
                                class="overflow-x-auto rounded-lg bg-black/80 p-3 pr-16 font-mono text-xs text-zinc-300 ring-1 ring-zinc-800/50 transition-all duration-300 group-hover:ring-zinc-700 sm:p-4 sm:text-sm"
                            >
                                <button
                                    onclick={(e) =>
                                        copyToClipboard(
                                            'cd ../backend && pip install -e .[api,dev]\ncd ../frontend && npm install',
                                            e.currentTarget
                                        )}
                                    class="absolute top-3 right-3 z-10 rounded border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-xs font-medium text-zinc-400 shadow-lg transition-all hover:border-zinc-600 hover:bg-zinc-700 hover:text-white"
                                    >copy</button
                                >
                                <div class="whitespace-nowrap">
                                    cd ../backend && pip install -e .[api,dev]
                                </div>
                                <div class="mt-1 whitespace-nowrap">
                                    cd ../frontend && npm install
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="group">
                        <div
                            class="mb-2.5 flex items-center gap-2.5 text-sm font-semibold text-zinc-300 lowercase sm:mb-3 sm:gap-3 sm:text-base"
                        >
                            <span
                                class="flex h-7 w-7 items-center justify-center rounded-lg bg-pink-500/10 text-xs font-bold text-pink-400 ring-1 ring-pink-500/30 backdrop-blur-sm transition-all duration-300 group-hover:scale-110 group-hover:bg-pink-500/20 group-hover:ring-pink-500/50 sm:h-8 sm:w-8 sm:text-sm"
                                >3</span
                            >
                            start development
                        </div>
                        <div class="relative ml-0 sm:ml-11">
                            <div
                                class="overflow-x-auto rounded-lg bg-black/80 p-3 pr-16 font-mono text-xs text-zinc-300 ring-1 ring-zinc-800/50 transition-all duration-300 group-hover:ring-zinc-700 sm:p-4 sm:text-sm"
                            >
                                <button
                                    onclick={(e) =>
                                        copyToClipboard(
                                            'uvicorn api.main:app --reload\nnpm run dev',
                                            e.currentTarget
                                        )}
                                    class="absolute top-3 right-3 z-10 rounded border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-xs font-medium text-zinc-400 shadow-lg transition-all hover:border-zinc-600 hover:bg-zinc-700 hover:text-white"
                                    >copy</button
                                >
                                <div class="whitespace-nowrap">
                                    backend: uvicorn api.main:app --reload
                                </div>
                                <div class="mt-1 whitespace-nowrap">frontend: npm run dev</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Features -->
            <div
                class="fade-in-up mt-16 grid w-full max-w-6xl grid-cols-1 gap-4 px-0 sm:mt-20 sm:grid-cols-2 sm:gap-6 lg:grid-cols-3"
                style="animation-delay: 0.5s;"
            >
                <div
                    class="group rounded-xl bg-zinc-900/40 p-5 ring-1 ring-zinc-800/50 backdrop-blur-md transition-all duration-300 hover:scale-105 hover:bg-zinc-900/60 hover:shadow-2xl hover:shadow-blue-500/10 hover:ring-blue-500/30 sm:p-6"
                >
                    <div class="mb-3 flex items-center justify-center gap-3 sm:mb-4 sm:block">
                        <div
                            class="text-3xl transition-transform duration-300 group-hover:scale-110 sm:text-4xl"
                        >
                            ⚡
                        </div>
                        <h3
                            class="m-0 bg-linear-to-r from-blue-400 to-blue-600 bg-clip-text text-base font-semibold text-transparent lowercase sm:mt-2 sm:mb-2 sm:text-lg"
                        >
                            type safe
                        </h3>
                    </div>
                    <p class="text-xs leading-relaxed text-zinc-400 lowercase sm:text-sm">
                        OpenAPI-generated TypeScript types. compile-time API validation.
                    </p>
                </div>

                <div
                    class="group rounded-xl bg-zinc-900/40 p-5 ring-1 ring-zinc-800/50 backdrop-blur-md transition-all duration-300 hover:scale-105 hover:bg-zinc-900/60 hover:shadow-2xl hover:shadow-purple-500/10 hover:ring-purple-500/30 sm:p-6"
                >
                    <div class="mb-3 flex items-center justify-center gap-3 sm:mb-4 sm:block">
                        <div
                            class="text-3xl transition-transform duration-300 group-hover:scale-110 sm:text-4xl"
                        >
                            🧪
                        </div>
                        <h3
                            class="m-0 bg-linear-to-r from-purple-400 to-purple-600 bg-clip-text text-base font-semibold text-transparent lowercase sm:mt-2 sm:mb-2 sm:text-lg"
                        >
                            fully tested
                        </h3>
                    </div>
                    <p class="text-xs leading-relaxed text-zinc-400 lowercase sm:text-sm">
                        pytest + async fixtures. API, SDK, and E2E test structure ready.
                    </p>
                </div>

                <div
                    class="group rounded-xl bg-zinc-900/40 p-5 ring-1 ring-zinc-800/50 backdrop-blur-md transition-all duration-300 hover:scale-105 hover:bg-zinc-900/60 hover:shadow-2xl hover:shadow-pink-500/10 hover:ring-pink-500/30 sm:col-span-2 sm:p-6 lg:col-span-1"
                >
                    <div class="mb-3 flex items-center justify-center gap-3 sm:mb-4 sm:block">
                        <div
                            class="text-3xl transition-transform duration-300 group-hover:scale-110 sm:text-4xl"
                        >
                            🐳
                        </div>
                        <h3
                            class="m-0 bg-linear-to-r from-pink-400 to-pink-600 bg-clip-text text-base font-semibold text-transparent lowercase sm:mt-2 sm:mb-2 sm:text-lg"
                        >
                            Docker ready
                        </h3>
                    </div>
                    <p class="text-xs leading-relaxed text-zinc-400 lowercase sm:text-sm">
                        PostgreSQL 17, Nginx, dev/prod profiles. one command to start.
                    </p>
                </div>
            </div>
        </section>

        <!-- Footer -->
        <footer class="mt-20 border-t border-zinc-800/50 bg-black/40 backdrop-blur-md">
            <div
                class="w-full px-5 py-6 text-center text-xs text-zinc-500 lowercase sm:py-8 sm:text-sm"
            >
                <p class="flex flex-wrap items-center justify-center gap-x-2 gap-y-1">
                    <span>built by</span>
                    <a
                        href="https://nokodo.net"
                        class="font-medium text-zinc-300 transition-all duration-300 hover:text-blue-400"
                        >nokodo labs</a
                    >
                    <span class="text-zinc-700">•</span>
                    <a
                        href="https://nokodo.net/github"
                        class="font-medium text-zinc-300 transition-all duration-300 hover:text-purple-400"
                        >github</a
                    >
                    <span class="text-zinc-700">•</span>
                    <span>licensed under</span>
                    <a
                        href="https://github.com/nokodo-labs/monorepo-template/blob/main/LICENSE"
                        class="font-medium text-zinc-300 transition-all duration-300 hover:text-pink-400"
                        >BSD 3-clause</a
                    >
                </p>
            </div>
        </footer>
    </div>
</main>
