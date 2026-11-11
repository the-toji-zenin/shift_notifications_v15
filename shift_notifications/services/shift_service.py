# Copyright (c) 2026, Ahmad and contributors
# For license information, please see license.txt

from datetime import datetime, timedelta
import frappe
from frappe.utils import get_datetime, getdate, add_days, now_datetime
from hrms.hr.doctype.shift_assignment.shift_assignment import get_shift_details


class ShiftService:
	@staticmethod
	def get_active_shift_assignments(eval_datetime: datetime | None = None) -> list[dict]:
		"""
		Returns all active, submitted Shift Assignments that could be relevant
		for the evaluation datetime (eval_date - 1 day to eval_date + 1 day to account for overnight shifts).
		"""
		if not eval_datetime:
			eval_datetime = now_datetime()

		eval_date = eval_datetime.date()
		prev_date = add_days(eval_date, -1)
		next_date = add_days(eval_date, 1)

		# Fetch active Shift Assignments
		assignments = frappe.db.sql(
			"""
			SELECT
				sa.name AS assignment_name,
				sa.employee,
				sa.shift_type,
				sa.start_date,
				sa.end_date,
				emp.employee_name,
				emp.user_id,
				emp.status AS employee_status
			FROM `tabShift Assignment` sa
			JOIN `tabEmployee` emp ON emp.name = sa.employee
			WHERE
				sa.docstatus = 1
				AND sa.status = 'Active'
				AND emp.status = 'Active'
				AND sa.start_date <= %(next_date)s
				AND (sa.end_date IS NULL OR sa.end_date >= %(prev_date)s)
			ORDER BY sa.start_date ASC
			""",
			{"prev_date": prev_date, "next_date": next_date},
			as_dict=True,
		)
		return assignments

	@staticmethod
	def resolve_shift_timings(shift_type: str, for_datetime: datetime | None = None) -> dict | None:
		"""
		Resolves scheduled and actual start/end datetimes for a Shift Type
		for a given timestamp using HRMS's get_shift_details.
		"""
		if not shift_type:
			return None

		if not for_datetime:
			for_datetime = now_datetime()

		try:
			details = get_shift_details(shift_type, for_timestamp=for_datetime)
			if not details or not details.get("start_datetime"):
				return None

			start_datetime = details["start_datetime"]
			end_datetime = details["end_datetime"]
			is_overnight = end_datetime.date() > start_datetime.date() or details["shift_type"].start_time > details["shift_type"].end_time

			return {
				"shift_type": shift_type,
				"start_datetime": start_datetime,
				"end_datetime": end_datetime,
				"actual_start": details.get("actual_start", start_datetime),
				"actual_end": details.get("actual_end", end_datetime),
				"is_overnight": is_overnight,
			}
		except Exception as e:
			frappe.log_error(f"ShiftService.resolve_shift_timings error: {e}", "Shift Notifications")
			return None

	@staticmethod
	def get_applicable_shift_windows_for_date(shift_type: str, target_date: datetime.date) -> list[dict]:
		"""
		Returns candidate shift timing windows anchored on target_date and target_date - 1 (for overnight).
		"""
		shift_type_doc = frappe.get_cached_doc("Shift Type", shift_type)
		start_time = shift_type_doc.start_time
		end_time = shift_type_doc.end_time

		windows = []

		# 1. Shift starting on target_date
		start_dt_today = datetime.combine(target_date, datetime.min.time()) + start_time
		if start_time > end_time:
			# Crosses midnight into next day
			end_dt_today = datetime.combine(add_days(target_date, 1), datetime.min.time()) + end_time
		else:
			end_dt_today = datetime.combine(target_date, datetime.min.time()) + end_time

		windows.append({
			"shift_type": shift_type,
			"start_datetime": start_dt_today,
			"end_datetime": end_dt_today,
			"anchor_date": target_date,
			"is_overnight": start_time > end_time,
		})

		# 2. Shift that started on previous day (if overnight)
		if start_time > end_time:
			prev_date = add_days(target_date, -1)
			start_dt_prev = datetime.combine(prev_date, datetime.min.time()) + start_time
			end_dt_prev = datetime.combine(target_date, datetime.min.time()) + end_time
			windows.append({
				"shift_type": shift_type,
				"start_datetime": start_dt_prev,
				"end_datetime": end_dt_prev,
				"anchor_date": prev_date,
				"is_overnight": True,
			})

		return windows
