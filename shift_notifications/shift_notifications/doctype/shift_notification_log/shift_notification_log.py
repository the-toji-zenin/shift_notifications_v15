# Copyright (c) 2026, Ahmad and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ShiftNotificationLog(Document):
	def before_insert(self):
		if not self.actual_sent_datetime and self.delivery_status == "Sent":
			self.actual_sent_datetime = frappe.utils.now_datetime()
		if not self.employee_name and self.employee:
			self.employee_name = frappe.db.get_value("Employee", self.employee, "employee_name")
