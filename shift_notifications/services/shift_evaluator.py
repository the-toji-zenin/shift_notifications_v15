# Copyright (c) 2026, Ahmad and contributors
# For license information, please see license.txt

from datetime import datetime, timedelta
import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime, format_time, format_date

from shift_notifications.shift_notifications.doctype.shift_notification_settings.shift_notification_settings import (
	get_settings,
)
from shift_notifications.services.shift_service import ShiftService
from shift_notifications.services.attendance_service import AttendanceService
from shift_notifications.services.notification_service import NotificationService


class ShiftEvaluator:
	@staticmethod
	def evaluate_and_dispatch_all(eval_datetime: datetime | None = None) -> dict:
		"""
		Main evaluation engine called periodically by the scheduler.
		Evaluates all active employee shift assignments against the 4 notification rules.
		"""
		if not eval_datetime:
			eval_datetime = now_datetime()

		settings = get_settings()
		if not settings.enable_shift_notifications:
			return {"status": "disabled", "evaluated": 0, "dispatched": 0}

		assignments = ShiftService.get_active_shift_assignments(eval_datetime)
		total_evaluated = 0
		total_dispatched = 0

		# Cache for leaves and holidays during this run to optimize batch processing
		leave_cache = {}
		holiday_cache = {}

		for sa in assignments:
			total_evaluated += 1
			try:
				dispatched = ShiftEvaluator._evaluate_single_assignment(
					sa=sa,
					eval_datetime=eval_datetime,
					settings=settings,
					leave_cache=leave_cache,
					holiday_cache=holiday_cache,
				)
				if dispatched:
					total_dispatched += 1
			except Exception as e:
				frappe.log_error(
					f"Error evaluating shift notification for {sa.employee} ({sa.assignment_name}): {e}",
					"Shift Notifications",
				)

		return {
			"status": "success",
			"evaluated": total_evaluated,
			"dispatched": total_dispatched,
			"eval_datetime": str(eval_datetime),
		}

	@staticmethod
	def _evaluate_single_assignment(
		sa: dict,
		eval_datetime: datetime,
		settings: object,
		leave_cache: dict,
		holiday_cache: dict,
	) -> bool:
		employee = sa.employee
		user_id = sa.user_id
		shift_type = sa.shift_type
		assignment_name = sa.assignment_name

		windows = ShiftService.get_applicable_shift_windows_for_date(shift_type, eval_datetime.date())
		any_dispatched = False

		for win in windows:
			start_dt = win["start_datetime"]
			end_dt = win["end_datetime"]
			anchor_date = win["anchor_date"]

			# 1. Skip if on approved leave
			leave_key = (employee, anchor_date)
			if leave_key not in leave_cache:
				leave_cache[leave_key] = AttendanceService.is_on_approved_leave(employee, anchor_date)
			if leave_cache[leave_key]:
				continue

			# 2. Skip if holiday / weekly off
			holiday_key = (employee, anchor_date)
			if holiday_key not in holiday_cache:
				holiday_cache[holiday_key] = AttendanceService.is_holiday(employee, anchor_date)
			if holiday_cache[holiday_key]:
				continue

			# 3. Retrieve punches for this shift
			punches = AttendanceService.get_shift_punches(employee, start_dt, end_dt)
			has_in = punches["has_in"]
			has_out = punches["has_out"]

			# ---------------------------------------------------------
			# RULE 1: Shift Starting Reminder
			# ---------------------------------------------------------
			if settings.enable_shift_starting_reminder and not has_in:
				remind_mins = settings.shift_starting_reminder_before_minutes or 10
				window_start = start_dt - timedelta(minutes=remind_mins)

				# Active window: between (start_dt - remind_mins) and start_dt
				if window_start <= eval_datetime < start_dt:
					message = _(
						"Your shift starts in {0} minutes ({1}). Please remember to check in."
					).format(remind_mins, format_time(start_dt.time()))

					dispatched = NotificationService.send_shift_notification(
						employee=employee,
						user_id=user_id,
						shift_assignment=assignment_name,
						shift_type=shift_type,
						notification_type="Shift Starting",
						scheduled_datetime=start_dt,
						message=message,
						settings=settings,
					)
					if dispatched:
						any_dispatched = True

			# ---------------------------------------------------------
			# RULE 2: Missed Check-in Reminder
			# ---------------------------------------------------------
			if settings.enable_missed_checkin_reminder and not has_in:
				grace_mins = settings.missed_checkin_reminder_after_minutes or 15
				trigger_time = start_dt + timedelta(minutes=grace_mins)

				# Active window: after (start_dt + grace_mins) and before shift ends
				if trigger_time <= eval_datetime < end_dt:
					message = _(
						"You have not checked in yet. Your scheduled shift started at {0}. Please check in."
					).format(format_time(start_dt.time()))

					dispatched = NotificationService.send_shift_notification(
						employee=employee,
						user_id=user_id,
						shift_assignment=assignment_name,
						shift_type=shift_type,
						notification_type="Missed Check-in",
						scheduled_datetime=start_dt,
						message=message,
						settings=settings,
					)
					if dispatched:
						any_dispatched = True

			# ---------------------------------------------------------
			# RULE 3: Upcoming Checkout Reminder
			# ---------------------------------------------------------
			if settings.enable_upcoming_checkout_reminder and has_in and not has_out:
				remind_mins = settings.upcoming_checkout_reminder_before_minutes or 15
				window_start = end_dt - timedelta(minutes=remind_mins)

				# Active window: between (end_dt - remind_mins) and end_dt
				if window_start <= eval_datetime < end_dt:
					message = _(
						"Your shift ends in {0} minutes ({1}). Please remember to check out."
					).format(remind_mins, format_time(end_dt.time()))

					dispatched = NotificationService.send_shift_notification(
						employee=employee,
						user_id=user_id,
						shift_assignment=assignment_name,
						shift_type=shift_type,
						notification_type="Upcoming Checkout",
						scheduled_datetime=end_dt,
						message=message,
						settings=settings,
					)
					if dispatched:
						any_dispatched = True

			# ---------------------------------------------------------
			# RULE 4: Missed Checkout Reminder
			# ---------------------------------------------------------
			if settings.enable_missed_checkout_reminder and has_in and not has_out:
				grace_mins = settings.missed_checkout_reminder_after_minutes or 15
				trigger_time = end_dt + timedelta(minutes=grace_mins)

				# Active window: after (end_dt + grace_mins) up to 12 hours after shift
				if trigger_time <= eval_datetime < (end_dt + timedelta(hours=12)):
					message = _(
						"Your scheduled shift ended at {0}, but no checkout record was found. Please complete your checkout."
					).format(format_time(end_dt.time()))

					dispatched = NotificationService.send_shift_notification(
						employee=employee,
						user_id=user_id,
						shift_assignment=assignment_name,
						shift_type=shift_type,
						notification_type="Missed Checkout",
						scheduled_datetime=end_dt,
						message=message,
						settings=settings,
					)
					if dispatched:
						any_dispatched = True

		return any_dispatched
