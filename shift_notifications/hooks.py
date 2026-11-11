app_name = "shift_notifications"
app_title = "Shift Notifications"
app_publisher = "Ahmad"
app_description = "A custom Frappe HRMS v15 application that manages automated employee shift notifications and reminders, including shift start alerts, missed check-in reminders, upcoming checkout alerts, and missed checkout notifications."
app_email = "ahmadpashashaiks@gmail.com"
app_license = "mit"

# Required Apps
required_apps = ["erpnext", "hrms"]

# Scheduled Tasks
# ---------------
scheduler_events = {
	"cron": {
		"* * * * *": [
			"shift_notifications.tasks.check_shift_reminders.trigger_shift_reminders"
		]
	},
	"daily": [
		"shift_notifications.tasks.check_shift_reminders.cleanup_old_notification_logs"
	],
}

# Testing
# -------
before_tests = "shift_notifications.tests.test_shift_notifications.before_tests"
