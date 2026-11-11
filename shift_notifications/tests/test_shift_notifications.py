# Copyright (c) 2026, Ahmad and contributors
# For license information, please see license.txt

import unittest
from datetime import datetime, timedelta, time
import frappe
from frappe.utils import now_datetime, getdate, add_days

from shift_notifications.services.shift_service import ShiftService
from shift_notifications.services.attendance_service import AttendanceService
from shift_notifications.services.notification_service import NotificationService
from shift_notifications.services.shift_evaluator import ShiftEvaluator
from shift_notifications.api.employee_shift import get_my_shift_status


def before_tests():
	frappe.set_user("Administrator")


class TestShiftNotifications(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.cleanup_test_data()
		self.setup_test_entities()

	def tearDown(self):
		self.cleanup_test_data()

	def setup_test_entities(self):
		# 1. Setup Test Settings
		settings = frappe.get_single("Shift Notification Settings")
		settings.enable_shift_notifications = 1
		settings.notification_channel = "Both"
		settings.enable_shift_starting_reminder = 1
		settings.shift_starting_reminder_before_minutes = 10
		settings.enable_missed_checkin_reminder = 1
		settings.missed_checkin_reminder_after_minutes = 15
		settings.enable_upcoming_checkout_reminder = 1
		settings.upcoming_checkout_reminder_before_minutes = 15
		settings.enable_missed_checkout_reminder = 1
		settings.missed_checkout_reminder_after_minutes = 15
		settings.enable_push_notifications = 1
		settings.enable_system_notifications = 1
		settings.save(ignore_permissions=True)

		# 2. Setup Test Shift Type
		if not frappe.db.exists("Shift Type", "Test Day Shift"):
			st = frappe.new_doc("Shift Type")
			st.name = "Test Day Shift"
			st.start_time = "09:00:00"
			st.end_time = "17:00:00"
			st.enable_auto_attendance = 0
			st.insert(ignore_permissions=True)

		# 3. Setup Test Overnight Shift
		if not frappe.db.exists("Shift Type", "Test Night Shift"):
			st_night = frappe.new_doc("Shift Type")
			st_night.name = "Test Night Shift"
			st_night.start_time = "22:00:00"
			st_night.end_time = "06:00:00"
			st_night.enable_auto_attendance = 0
			st_night.insert(ignore_permissions=True)

		# 4. Setup Test Employee
		self.test_user = "test_shift_emp@example.com"

		# Setup Test Gender (Employee gender is a Link field; also needed by User->Contact)
		if not frappe.db.exists("Gender", "Male"):
			gender = frappe.new_doc("Gender")
			gender.gender = "Male"
			gender.insert(ignore_permissions=True)

		# Setup Test Company (Employee requires a company)
		if not frappe.db.exists("Company", "Test Company"):
			company = frappe.new_doc("Company")
			company.company_name = "Test Company"
			company.abbr = "TC"
			company.country = "India"
			company.default_currency = "INR"
			company.insert(ignore_permissions=True)

		if not frappe.db.exists("User", self.test_user):
			user = frappe.new_doc("User")
			user.email = self.test_user
			user.first_name = "Shift Test"
			user.send_welcome_email = 0
			user.insert(ignore_permissions=True)

		self.test_emp_name = "TEST-EMP-SHIFT-01"

		if not frappe.db.exists("Employee", self.test_emp_name):
			emp = frappe.new_doc("Employee")
			emp.name = self.test_emp_name
			emp.first_name = "Shift Test Employee"
			emp.user_id = self.test_user
			emp.status = "Active"
			emp.gender = "Male"
			emp.date_of_birth = "1990-01-01"
			emp.company = "Test Company"
			emp.date_of_joining = "2020-01-01"
			emp.insert(ignore_permissions=True)

		# 5. Assign Shift
		today = getdate()
		self.assignment = frappe.new_doc("Shift Assignment")
		self.assignment.employee = self.test_emp_name
		self.assignment.shift_type = "Test Day Shift"
		self.assignment.start_date = add_days(today, -5)
		self.assignment.end_date = add_days(today, 5)
		self.assignment.status = "Active"
		self.assignment.company = "Test Company"
		self.assignment.insert(ignore_permissions=True)
		self.assignment.submit()

	def cleanup_test_data(self):
		frappe.db.sql("DELETE FROM `tabShift Notification Log` WHERE employee LIKE 'TEST-EMP%'")
		frappe.db.sql("DELETE FROM `tabEmployee Checkin` WHERE employee LIKE 'TEST-EMP%'")
		frappe.db.sql("DELETE FROM `tabShift Assignment` WHERE employee LIKE 'TEST-EMP%'")
		# Remove test Employee (unlinks the user) and User so user_id can be reassigned each run
		frappe.db.sql("DELETE FROM `tabEmployee` WHERE user_id = 'test_shift_emp@example.com' OR name = 'TEST-EMP-SHIFT-01'")
		frappe.db.sql("DELETE FROM `tabUser` WHERE email = 'test_shift_emp@example.com'")
		frappe.db.sql("DELETE FROM `tabCompany` WHERE name = 'Test Company'")
		frappe.db.sql("DELETE FROM `tabGender` WHERE gender = 'Male'")
		frappe.db.commit()

	# -------------------------------------------------------------
	# Test 1: Shift Starting Reminder
	# -------------------------------------------------------------
	def test_shift_starting_reminder(self):
		today = getdate()
		# Shift starts at 09:00:00. Eval at 08:52:00 (8 minutes before, within 10-minute window)
		eval_dt = datetime.combine(today, time(8, 52, 0))

		res = ShiftEvaluator.evaluate_and_dispatch_all(eval_dt)
		print("DEBUG dispatched:", res, "emp:", self.test_emp_name)
		self.assertGreaterEqual(res["dispatched"], 1)

		# Verify log created
		log = frappe.db.get_value(
			"Shift Notification Log",
			{"employee": self.test_emp_name, "notification_type": "Shift Starting"},
			["name", "delivery_status", "idempotency_key"],
			as_dict=True,
		)
		self.assertIsNotNone(log)
		self.assertIn(log.delivery_status, ["Sent", "Pending", "Failed"])

	# -------------------------------------------------------------
	# Test 2: Idempotency (Duplicate Prevention)
	# -------------------------------------------------------------
	def test_duplicate_prevention(self):
		today = getdate()
		eval_dt = datetime.combine(today, time(8, 52, 0))

		# First run
		res1 = ShiftEvaluator.evaluate_and_dispatch_all(eval_dt)
		self.assertEqual(res1["dispatched"], 1)

		# Second run at same time (simulating concurrent/repeated scheduler tick)
		res2 = ShiftEvaluator.evaluate_and_dispatch_all(eval_dt)
		self.assertEqual(res2["dispatched"], 0)

		# Verify only 1 log document exists
		count = frappe.db.count("Shift Notification Log", {"employee": self.test_emp_name, "notification_type": "Shift Starting"})
		self.assertEqual(count, 1)

	# -------------------------------------------------------------
	# Test 3: No Reminder If Already Checked In
	# -------------------------------------------------------------
	def test_no_reminder_if_already_checked_in(self):
		today = getdate()
		# Punch IN at 08:45:00
		checkin = frappe.new_doc("Employee Checkin")
		checkin.employee = self.test_emp_name
		checkin.log_type = "IN"
		checkin.time = datetime.combine(today, time(8, 45, 0))
		checkin.insert(ignore_permissions=True)

		# Evaluate at 08:52:00
		eval_dt = datetime.combine(today, time(8, 52, 0))
		res = ShiftEvaluator.evaluate_and_dispatch_all(eval_dt)
		self.assertEqual(res["dispatched"], 0)

	# -------------------------------------------------------------
	# Test 4: Missed Check-in Reminder
	# -------------------------------------------------------------
	def test_missed_checkin_reminder(self):
		today = getdate()
		# Shift started at 09:00:00. Eval at 09:20:00 (20 mins after, grace is 15 mins)
		eval_dt = datetime.combine(today, time(9, 20, 0))

		res = ShiftEvaluator.evaluate_and_dispatch_all(eval_dt)
		self.assertGreaterEqual(res["dispatched"], 1)

		log = frappe.db.get_value(
			"Shift Notification Log",
			{"employee": self.test_emp_name, "notification_type": "Missed Check-in"},
			"name",
		)
		self.assertIsNotNone(log)

	# -------------------------------------------------------------
	# Test 5: Upcoming Checkout Reminder
	# -------------------------------------------------------------
	def test_upcoming_checkout_reminder(self):
		today = getdate()
		# Checked in at 09:00:00
		checkin = frappe.new_doc("Employee Checkin")
		checkin.employee = self.test_emp_name
		checkin.log_type = "IN"
		checkin.time = datetime.combine(today, time(9, 0, 0))
		checkin.insert(ignore_permissions=True)

		# Shift ends at 17:00:00. Eval at 16:50:00 (10 mins before, within 15-min window)
		eval_dt = datetime.combine(today, time(16, 50, 0))
		res = ShiftEvaluator.evaluate_and_dispatch_all(eval_dt)
		self.assertGreaterEqual(res["dispatched"], 1)

		log = frappe.db.get_value(
			"Shift Notification Log",
			{"employee": self.test_emp_name, "notification_type": "Upcoming Checkout"},
			"name",
		)
		self.assertIsNotNone(log)

	# -------------------------------------------------------------
	# Test 6: No Reminder After Checkout
	# -------------------------------------------------------------
	def test_no_reminder_after_checkout(self):
		today = getdate()
		# IN at 09:00, OUT at 16:45
		cin = frappe.new_doc("Employee Checkin")
		cin.employee = self.test_emp_name
		cin.log_type = "IN"
		cin.time = datetime.combine(today, time(9, 0, 0))
		cin.insert(ignore_permissions=True)

		cout = frappe.new_doc("Employee Checkin")
		cout.employee = self.test_emp_name
		cout.log_type = "OUT"
		cout.time = datetime.combine(today, time(16, 45, 0))
		cout.insert(ignore_permissions=True)

		# Eval at 16:50:00
		eval_dt = datetime.combine(today, time(16, 50, 0))
		res = ShiftEvaluator.evaluate_and_dispatch_all(eval_dt)
		self.assertEqual(res["dispatched"], 0)

	# -------------------------------------------------------------
	# Test 7: Missed Checkout Reminder
	# -------------------------------------------------------------
	def test_missed_checkout_reminder(self):
		today = getdate()
		# IN at 09:00, no OUT
		cin = frappe.new_doc("Employee Checkin")
		cin.employee = self.test_emp_name
		cin.log_type = "IN"
		cin.time = datetime.combine(today, time(9, 0, 0))
		cin.insert(ignore_permissions=True)

		# Shift ends at 17:00:00. Eval at 17:25:00 (25 mins after, grace is 15 mins)
		eval_dt = datetime.combine(today, time(17, 25, 0))
		res = ShiftEvaluator.evaluate_and_dispatch_all(eval_dt)
		self.assertGreaterEqual(res["dispatched"], 1)

		log = frappe.db.get_value(
			"Shift Notification Log",
			{"employee": self.test_emp_name, "notification_type": "Missed Checkout"},
			"name",
		)
		self.assertIsNotNone(log)

	# -------------------------------------------------------------
	# Test 8: Overnight Shift Handling
	# -------------------------------------------------------------
	def test_overnight_shift_windows(self):
		today = getdate()
		windows = ShiftService.get_applicable_shift_windows_for_date("Test Night Shift", today)
		self.assertEqual(len(windows), 2)

		# Today's shift (starts 22:00 today, ends 06:00 tomorrow)
		win_today = windows[0]
		self.assertTrue(win_today["is_overnight"])
		self.assertEqual(win_today["end_datetime"].date(), add_days(today, 1))

		# Yesterday's shift (started 22:00 yesterday, ends 06:00 today)
		win_prev = windows[1]
		self.assertTrue(win_prev["is_overnight"])
		self.assertEqual(win_prev["end_datetime"].date(), today)

	# -------------------------------------------------------------
	# Test 9: Employee Shift Status API
	# -------------------------------------------------------------
	def test_get_my_shift_status_api(self):
		frappe.set_user(self.test_user)
		status = get_my_shift_status()

		self.assertTrue(status["has_employee"])
		self.assertTrue(status["has_shift"])
		self.assertEqual(status["employee"], self.test_emp_name)
		self.assertEqual(status["shift_type"], "Test Day Shift")
		self.assertIn("shift_start", status)
		self.assertIn("shift_end", status)
		self.assertIn("remaining_seconds", status)
		self.assertIn("upcoming_checkout_warning", status)
