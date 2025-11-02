<script lang="ts">
  let count = $state(0)

  function increment() {
    count += 1
  }
</script>

<div class="mb-4 text-center">
  <button
    onclick={increment}
    class="rounded-lg bg-indigo-600 px-6 py-3 text-lg font-semibold text-white shadow-lg transition-all hover:bg-indigo-700 hover:shadow-xl"
  >
    Count is {count}
  </button>
  <p class="mt-2 text-sm text-gray-600 dark:text-gray-400">
    Click the button to increment
  </p>
</div>
