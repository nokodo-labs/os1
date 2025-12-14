<script lang="ts">
	import { goto } from "$app/navigation";
	import ChatInputLiquidGlass from "$lib/components/chat/ChatInput.svelte";
	import { fade } from "svelte/transition";

	let inputValue = $state("");
	let isGenerating = $state(false);

	function handleSendMessage(content: string) {
		// Create a new thread ID (mock)
		const threadId = Date.now().toString();
		// Navigate to the chat page with the initial message
		goto(`/chats/${threadId}?q=${encodeURIComponent(content)}`);
	}

	function handleStopGeneration() {
		isGenerating = false;
	}
</script>

<!-- Input Area (Fixed Bottom) -->
<div class="absolute right-0 bottom-0 left-0 z-10 pt-10 pb-8">
	<div class="mx-auto w-full max-w-4xl px-8">
		<div
			class="transition-all duration-500 ease-in-out -translate-y-[40vh]"
		>
			<div
				class="mb-8 flex flex-col items-center justify-center gap-2 text-center"
				transition:fade={{ duration: 200 }}
			>
				<h1 class="text-4xl font-medium text-white">
					hi <span
						class="bg-clip-text text-transparent [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]"
						style="background-image: linear-gradient(to bottom right, var(--accent-secondary), var(--accent-primary));"
						>simone</span
					>
				</h1>
				<p class="text-xl text-white/60">good afternoon</p>
			</div>
			<ChatInputLiquidGlass
				bind:value={inputValue}
				onSubmit={handleSendMessage}
				onStop={handleStopGeneration}
				{isGenerating}
				placeholder="send a message"
			/>
		</div>
	</div>
</div>
