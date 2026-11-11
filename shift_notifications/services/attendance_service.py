# Copyright (c) 2026, Ahmad and contributors
# For license information, please see license.txt

from datetime import datetime, timedelta
import frappe
from frappe.utils import getdate, get_datetime, add_days
from erpnext.setup.doctype.employee.employee import is_holiday, get_holiday_list_for_employee


class AttendanceService:
	@staticmethod
	def is_on_approved_leave(employee: str, check_date: datetime.date | str) -> bool:
		"""
		Checks if employee is on an approved Leave Application on check_date.
		"""
		check_date = getdate(check_date)
		return bool(
			frappe.db.exists(
				"Leave Application",
				{
					"employee": employee,
					"docstatus": 1,
					"status": "Approved",
					"from_date": ("<=", check_date),
					"to_date": (">=", check_date),
				},
			)
		)

	@staticmethod
	def is_holiday(employee: str, check_date: datetime.date | str) -> bool:
		"""
		Checks if check_date is a holiday or weekly off for the employee.
		"""
		check_date = getdate(check_date)
		try:
			holiday_list = get_holiday_list_for_employee(employee, raise_exception=False)
			if not holiday_list:
				return False
			return is_holiday(holiday_list, check_date)
		except Exception:
			return False

	@staticmethod
	def get_shift_punches(
		employee: str,
		shift_start: datetime,
		shift_end: datetime,
		pre_start_margin_minutes: int = 120,
		post_end_margin_minutes: int = 120,
	) -> dict:
		"""
		Retrieves IN and OUT punches for the employee within the designated shift window.
		"""
		window_start = shift_start - timedelta(minutes=pre_start_margin_minutes)
		window_end = shift_end + timedelta(minutes=post_end_margin_minutes)

		logs = frappe.db.sql(
			"""
			SELECT
				name,
				employee,
				log_type,
				time,
				shift
			FROM `tabEmployee Checkin`
			WHERE
				employee = %(employee)s
				AND time BETWEEN %(window_start)s AND %(window_end)s
			ORDER BY time ASC
			""",
			{
				"employee": employee,
				"window_start": window_start,
				"window_end": window_end,
			},
			as_dict=True,
		)

		has_in = False
		has_out = False
		first_in = None
		last_out = None
		last_punch = None

		for log in logs:
			last_punch = log
			# Check IN punches
			if log.log_type == "IN" and not has_in:
				has_in = True
				first_in = log
			# Check OUT punches
			elif log.log_type == "OUT":
				# Only consider OUT if it occurred after first_in or after shift start
				has_out = True
				last_out = log

		# If logs are alternating (log_type not strictly specified or alternating)
		if logs and not has_in and not has_out:
			# If log_type is missing or first entry exists
			first_log = logs[0]
			has_in = True
			first_in = first_log
			if len(logs) > 1:
				has_out = True
				last_out = logs[-1]

		return {
			"has_in": has_in,
			"has_out": has_out,
			"first_in": first_in,
			"last_out": last_out,
			"last_punch": last_punch,
			"total_punches": len(logs),
		}
