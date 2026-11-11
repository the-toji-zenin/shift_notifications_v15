<template>
	<div
		v-if="shiftStatus.data?.has_shift"
		class="w-full mt-3 p-3.5 rounded-lg border text-sm transition-all duration-300"
		:class="
			shiftStatus.data?.upcoming_checkout_warning
				? 'bg-amber-50 border-amber-300 text-amber-900 shadow-sm'
				: 'bg-gray-50 border-gray-200 text-gray-700'
		"
	>
		<!-- Shift Header -->
		<div class="flex items-center justify-between font-semibold">
			<span class="flex items-center gap-1.5">
				<FeatherIcon name="clock" class="w-4 h-4 text-gray-500" />
				{{ __("Current Shift") }}
			</span>
			<span class="text-xs bg-white px-2 py-0.5 rounded border text-gray-800 font-medium">
				{{ shiftStatus.data.shift_start_display }} – {{ shiftStatus.data.shift_end_display }}
			</span>
		</div>

		<!-- Checked In View: Countdown & Warnings -->
		<div
			v-if="shiftStatus.data?.is_checked_in && !shiftStatus.data?.is_checked_out"
			class="mt-2.5 pt-2 border-t border-dashed border-gray-300"
		>
			<div class="flex items-center justify-between">
				<span class="font-medium text-xs uppercase tracking-wider text-gray-500">
					{{ __("Upcoming Checkout") }}
				</span>
				<span
					class="font-bold text-sm tracking-wide"
					:class="shiftStatus.data?.upcoming_checkout_warning ? 'text-amber-700 font-mono text-base' : 'text-gray-900 font-mono'"
				>
					{{ formattedRemainingTime }}
				</span>
			</div>

			<!-- Warning Banner if within checkout threshold -->
			<div
				v-if="shiftStatus.data?.upcoming_checkout_warning"
				class="mt-2 p-2 bg-amber-100/70 rounded text-xs font-medium text-amber-900 flex items-start gap-1.5"
			>
				<FeatherIcon name="alert-circle" class="w-4 h-4 shrink-0 text-amber-600 mt-0.5" />
				<span class="leading-tight">
					{{ shiftStatus.data.warning_message || __("Your shift is ending soon. Please remember to check out.") }}
				</span>
			</div>
		</div>

		<!-- Not Checked In View -->
		<div
			v-else-if="!shiftStatus.data?.is_checked_in"
			class="mt-2 pt-2 border-t border-dashed border-gray-300 text-xs text-gray-600 flex items-center gap-1.5"
		>
			<FeatherIcon name="info" class="w-3.5 h-3.5 text-blue-500 shrink-0" />
			<span>
				{{ __("Scheduled shift starts at {0}. Please remember to check in.", [shiftStatus.data.shift_start_display]) }}
			</span>
		</div>
	</div>
</template>

<script setup>
import { createResource, FeatherIcon } from "frappe-ui"
import { computed, inject, ref, onMounted, onBeforeUnmount } from "vue"

const __ = inject("$translate") || ((x) => x)

const remainingSeconds = ref(0)
let timer = null
let syncTimer = null

const shiftStatus = createResource({
	url: "shift_notifications.api.employee_shift.get_my_shift_status",
	auto: true,
	onSuccess(data) {
		if (data && data.has_shift) {
			remainingSeconds.value = Math.max(0, data.remaining_seconds || 0)
		}
	},
})

const formattedRemainingTime = computed(() => {
	const s = remainingSeconds.value
	if (s <= 0) return __("0 minutes remaining")

	const hrs = Math.floor(s / 3600)
	const mins = Math.floor((s % 3600) / 60)
	const secs = s % 60

	if (hrs > 0) {
		return `${hrs}h ${mins}m ${secs}s`
	} else if (mins > 0) {
		return `${mins}m ${secs}s`
	} else {
		return `${secs}s`
	}
})

onMounted(() => {
	// Local second-by-second countdown without hitting server every second
	timer = setInterval(() => {
		if (remainingSeconds.value > 0) {
			remainingSeconds.value--
		}
	}, 1000)

	// Background resync every 60 seconds with server
	syncTimer = setInterval(() => {
		shiftStatus.fetch()
	}, 60000)
})

onBeforeUnmount(() => {
	if (timer) clearInterval(timer)
	if (syncTimer) clearInterval(syncTimer)
})
</script>
