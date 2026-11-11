# Copyright (c) 2026, Ahmad and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ShiftNotificationSettings(Document):
	def validate(self):
		if self.shift_starting_reminder_before_minutes < 0:
			frappe.throw(frappe._("Shift Starting Reminder minutes cannot be negative"))
		if self.missed_checkin_reminder_after_minutes < 0:
			frappe.throw(frappe._("Missed Check-in Reminder minutes cannot be negative"))
		if self.upcoming_checkout_reminder_before_minutes < 0:
			frappe.throw(frappe._("Upcoming Checkout Reminder minutes cannot be negative"))
		if self.missed_checkout_reminder_after_minutes < 0:
			frappe.throw(frappe._("Missed Checkout Reminder minutes cannot be negative"))


def get_settings():
	"""Helper function to get cached or fresh settings"""
	return frappe.get_single("Shift Notification Settings")
