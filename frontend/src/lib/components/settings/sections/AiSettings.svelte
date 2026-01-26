<div class="space-y-4">
	<div class="rounded-box bg-white/5 p-5">
		<div class="text-sm font-semibold text-white/85">default model</div>
		<div class="mt-1 text-sm text-white/55">
			choose the AI model used for conversations by default.
		</div>
		<div class="rounded-pill mt-4 h-10 w-full bg-white/8"></div>
	</div>
	<div class="rounded-box bg-white/5 p-5">
		<div class="text-sm font-semibold text-white/85">response style</div>
		<div class="mt-1 text-sm text-white/55">
			adjust how the AI responds: concise, balanced, or detailed.
		</div>
		<div class="mt-4 flex gap-2">
			{#each ['concise', 'balanced', 'detailed'] as style (style)}
				<button
					type="button"
					class="rounded-pill flex-1 border border-transparent bg-white/5 px-4 py-2.5 text-sm text-white/60 transition-all duration-200 hover:border-white/10 hover:bg-white/8 hover:text-white/80"
				>
					{style}
				</button>
			{/each}
		</div>
	</div>
</div>
