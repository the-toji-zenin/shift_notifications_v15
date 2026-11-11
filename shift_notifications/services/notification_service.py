# Copyright (c) 2026, Ahmad and contributors
# For license information, please see license.txt

from datetime import datetime
import frappe
from frappe import _
from frappe.utils import now_datetime, cstr


class NotificationService:
	@staticmethod
	def generate_idempotency_key(
		employee: str,
		shift_assignment: str,
		notification_type: str,
		scheduled_datetime: datetime,
	) -> str:
		"""
		Generates a stable, deterministic idempotency key for preventing duplicate notifications.
		Format: {TYPE}-{EMPLOYEE}-{ASSIGNMENT}-{YYYYMMDDHHMM}
		"""
		time_str = scheduled_datetime.strftime("%Y%m%d%H%M")
		type_slug = notification_type.upper().replace(" ", "-")
		return f"{type_slug}_{employee}_{shift_assignment}_{time_str}"

	@staticmethod
	def send_shift_notification(
		employee: str,
		user_id: str | None,
		shift_assignment: str,
		shift_type: str,
		notification_type: str,
		scheduled_datetime: datetime,
		message: str,
		settings: object,
	) -> bool:
		"""
		Atomically creates an idempotency log and dispatches the notification via configured channels.
		Returns True if dispatched successfully, False if skipped/failed/duplicate.
		"""
		idempotency_key = NotificationService.generate_idempotency_key(
			employee, shift_assignment, notification_type, scheduled_datetime
		)

		# 1. Quick check if already logged
		if frappe.db.exists("Shift Notification Log", {"idempotency_key": idempotency_key}):
			return False

		if not user_id:
			user_id = frappe.db.get_value("Employee", employee, "user_id")

		# 2. Atomic reservation: Insert log with 'Pending' status
		try:
			log_doc = frappe.new_doc("Shift Notification Log")
			log_doc.idempotency_key = idempotency_key
			log_doc.employee = employee
			log_doc.user = user_id
			log_doc.shift_assignment = shift_assignment
			log_doc.shift_type = shift_type
			log_doc.notification_type = notification_type
			log_doc.scheduled_notification_datetime = scheduled_datetime
			log_doc.delivery_status = "Pending"
			log_doc.message = message
			log_doc.channel = settings.notification_channel or "Both"
			log_doc.insert(ignore_permissions=True)
			frappe.db.commit()  # commit reservation
		except frappe.DuplicateEntryError:
			# Another worker already inserted this key
			frappe.db.rollback()
			return False
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(f"Failed to reserve notification log: {e}", "Shift Notifications")
			return False

		# 3. Dispatch across enabled channels
		sent_channels = []
		errors = []

		# Channel: PWA / Push Notification
		if settings.enable_push_notifications and settings.notification_channel in ["Push Notification", "Both"]:
			if user_id:
				try:
					NotificationService._dispatch_pwa_push(
						user_id=user_id,
						message=message,
						shift_assignment=shift_assignment,
						notification_type=notification_type,
					)
					sent_channels.append("PWA Push")
				except Exception as e:
					errors.append(f"Push Error: {cstr(e)}")
			else:
				errors.append("Skipped Push: Employee has no linked Frappe user")

		# Channel: System Notification (Desk Alert)
		if settings.enable_system_notifications and settings.notification_channel in ["System Notification", "Both"]:
			if user_id:
				try:
					NotificationService._dispatch_desk_system_notification(
						user_id=user_id,
						message=message,
						shift_assignment=shift_assignment,
					)
					sent_channels.append("System Notification")
				except Exception as e:
					errors.append(f"System Notification Error: {cstr(e)}")

		# 4. Finalize log status
		try:
			if sent_channels:
				log_doc.delivery_status = "Sent"
				log_doc.channel = ", ".join(sent_channels)
				log_doc.actual_sent_datetime = now_datetime()
				log_doc.error_message = "; ".join(errors) if errors else ""
			else:
				log_doc.delivery_status = "Failed" if errors else "Skipped"
				log_doc.error_message = "; ".join(errors) if errors else "No active delivery channels"

			log_doc.save(ignore_permissions=True)
			frappe.db.commit()
			return bool(sent_channels)
		except Exception as e:
			frappe.log_error(f"Failed to update notification log {log_doc.name}: {e}", "Shift Notifications")
			return False

	@staticmethod
	def _dispatch_pwa_push(user_id: str, message: str, shift_assignment: str, notification_type: str):
		"""
		Dispatches notification through HRMS PWA Notification DocType.
		This triggers FCM push and realtime websocket updates.
		"""
		pwa = frappe.new_doc("PWA Notification")
		pwa.to_user = user_id
		pwa.from_user = "Administrator"
		pwa.message = message
		pwa.reference_document_type = "Shift Assignment"
		pwa.reference_document_name = shift_assignment
		pwa.insert(ignore_permissions=True)

	@staticmethod
	def _dispatch_desk_system_notification(user_id: str, message: str, shift_assignment: str):
		"""
		Creates a standard Frappe Notification Log document for in-desk alerts.
		"""
		if not frappe.db.exists("DocType", "Notification Log"):
			return

		doc = frappe.new_doc("Notification Log")
		doc.for_user = user_id
		doc.type = "Alert"
		doc.document_type = "Shift Assignment"
		doc.document_name = shift_assignment
		doc.subject = message
		doc.insert(ignore_permissions=True)
