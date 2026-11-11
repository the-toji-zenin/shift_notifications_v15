# Copyright (c) 2026, Ahmad and contributors
# For license information, please see license.txt

from datetime import datetime
import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime, getdate, time_diff_in_seconds, format_time, format_datetime

from shift_notifications.shift_notifications.doctype.shift_notification_settings.shift_notification_settings import (
	get_settings,
)
from shift_notifications.services.shift_service import ShiftService
from shift_notifications.services.attendance_service import AttendanceService


@frappe.whitelist()
def get_my_shift_status() -> dict:
	"""
	Returns the authenticated employee's active shift status, timing, punch status,
	countdown to shift end, and upcoming checkout warning status.
	"""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)

	# 1. Resolve employee linked to current user
	employee = frappe.db.get_value(
		"Employee",
		{"user_id": user, "status": "Active"},
		["name", "employee_name", "default_shift", "company"],
		as_dict=True,
	)

	if not employee:
		return {
			"has_employee": False,
			"message": _("No active Employee profile linked to user {0}").format(user),
		}

	now_dt = now_datetime()
	eval_date = now_dt.date()

	# 2. Check for active Shift Assignment
	assignment = frappe.db.sql(
		"""
		SELECT
			name,
			shift_type,
			start_date,
			end_date
		FROM `tabShift Assignment`
		WHERE
			employee = %(employee)s
			AND docstatus = 1
			AND status = 'Active'
			AND start_date <= %(eval_date)s
			AND (end_date IS NULL OR end_date >= %(eval_date)s)
		ORDER BY start_date DESC
		LIMIT 1
		""",
		{"employee": employee.name, "eval_date": eval_date},
		as_dict=True,
	)

	shift_type_name = assignment[0].shift_type if assignment else employee.default_shift
	assignment_name = assignment[0].name if assignment else None

	if not shift_type_name:
		return {
			"has_employee": True,
			"has_shift": False,
			"employee": employee.name,
			"employee_name": employee.employee_name,
			"message": _("No shift assigned for today."),
		}

	# 3. Check leaves and holidays
	is_leave = AttendanceService.is_on_approved_leave(employee.name, eval_date)
	is_holiday_today = AttendanceService.is_holiday(employee.name, eval_date)

	# 4. Resolve candidate shift window
	windows = ShiftService.get_applicable_shift_windows_for_date(shift_type_name, eval_date)
	active_window = None

	for win in windows:
		# Check if now_dt falls inside or near the window
		start_dt = win["start_datetime"]
		end_dt = win["end_datetime"]
		# If within 4 hours before start or 12 hours after end
		if (start_dt - frappe.utils.timedelta(hours=4)) <= now_dt <= (end_dt + frappe.utils.timedelta(hours=12)):
			active_window = win
			break

	if not active_window and windows:
		active_window = windows[0]

	start_datetime = active_window["start_datetime"]
	end_datetime = active_window["end_datetime"]
	is_overnight = active_window.get("is_overnight", False)

	# 5. Retrieve punch logs
	punches = AttendanceService.get_shift_punches(employee.name, start_datetime, end_datetime)
	has_in = punches["has_in"]
	has_out = punches["has_out"]
	last_punch = punches["last_punch"]

	# 6. Calculate countdown and alert status
	remaining_seconds = 0
	remaining_minutes = 0
	upcoming_checkout_warning = False
	warning_message = ""

	settings = get_settings()
	warning_threshold = settings.upcoming_checkout_reminder_before_minutes or 15

	if now_dt < end_datetime:
		remaining_seconds = max(0, int(time_diff_in_seconds(end_datetime, now_dt)))
		remaining_minutes = max(0, round(remaining_seconds / 60))

	# Trigger checkout warning if checked in, not checked out, and within threshold
	if has_in and not has_out:
		if now_dt >= (end_datetime - frappe.utils.timedelta(minutes=warning_threshold)):
			upcoming_checkout_warning = True
			if now_dt < end_datetime:
				warning_message = _("Your shift is ending soon in {0} minutes. Please remember to check out.").format(
					remaining_minutes
				)
			else:
				overdue_mins = max(0, int((now_dt - end_datetime).total_seconds() / 60))
				warning_message = _("Your scheduled shift ended {0} minutes ago. Please complete your checkout.").format(
					overdue_mins
				)

	return {
		"has_employee": True,
		"has_shift": True,
		"employee": employee.name,
		"employee_name": employee.employee_name,
		"shift_assignment": assignment_name,
		"shift_type": shift_type_name,
		"shift_start": start_datetime.isoformat(),
		"shift_end": end_datetime.isoformat(),
		"shift_start_display": format_time(start_datetime.time()),
		"shift_end_display": format_time(end_datetime.time()),
		"is_overnight": is_overnight,
		"is_on_leave": is_leave,
		"is_holiday": is_holiday_today,
		"is_checked_in": has_in,
		"is_checked_out": has_out,
		"last_punch_type": last_punch.log_type if last_punch else None,
		"last_punch_time": last_punch.time.isoformat() if last_punch else None,
		"remaining_seconds": remaining_seconds,
		"remaining_minutes": remaining_minutes,
		"upcoming_checkout_warning": upcoming_checkout_warning,
		"warning_threshold_minutes": warning_threshold,
		"warning_message": warning_message,
		"server_time": now_dt.isoformat(),
	}
