# Copyright (c) 2026, Ahmad and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import now_datetime
from shift_notifications.services.shift_evaluator import ShiftEvaluator


def trigger_shift_reminders():
	"""
	Scheduled entry point called every minute via scheduler_events in hooks.py.
	"""
	try:
		return ShiftEvaluator.evaluate_and_dispatch_all(now_datetime())
	except Exception as e:
		frappe.log_error(f"Error in trigger_shift_reminders: {e}", "Shift Notifications Scheduler")


def cleanup_old_notification_logs():
	"""
	Daily task to purge notification logs older than the configured log_retention_days.
	"""
	try:
		settings = frappe.get_single("Shift Notification Settings")
		retention_days = settings.log_retention_days or 30
		frappe.db.sql(
			"""
			DELETE FROM `tabShift Notification Log`
			WHERE creation < DATE_SUB(NOW(), INTERVAL %s DAY)
			""",
			(retention_days,),
		)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(f"Error in cleanup_old_notification_logs: {e}", "Shift Notifications Cleanup")
