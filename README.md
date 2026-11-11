# Shift Notifications for Frappe HRMS (v15)

An enterprise-ready Frappe v15 application extending Frappe HRMS attendance functionality with automated, idempotent push and system notifications for employee shifts, and real-time shift countdown and near-checkout alerts on `/hrms/home`.

---

## Features

### 1. Shift Starting Reminder

* Automatically notifies employees before their scheduled shift begins (configurable, default: 10 minutes prior).
* Skips employees who have already punched IN, employees on approved leave, or employees on holidays/weekly offs.
* Message: *"Your shift starts in 10 minutes (09:00 AM). Please remember to check in."*

### 2. Missed Check-in Reminder

* Alerts employees who have not checked in after their scheduled shift has started and grace period elapsed (configurable, default: 15 minutes after start).
* Respects approved leave and holiday schedules.
* Message: *"You have not checked in yet. Your scheduled shift started at 09:00 AM. Please check in."*

### 3. Upcoming Checkout Reminder

* Notifies employees who are checked in as their scheduled shift end approaches (configurable, default: 15 minutes prior).
* Message: *"Your shift ends in 15 minutes (05:00 PM). Please remember to check out."*

### 4. Missed Checkout Reminder

* Alerts employees who checked in but have not checked out after their scheduled shift ended plus grace period (configurable, default: 15 minutes after end).
* Handles overnight and cross-midnight shifts accurately.
* Message: *"Your scheduled shift ended at 05:00 PM, but no checkout record was found. Please complete your checkout."*

### 5. Real-time Frontend Shift Status & Checkout Countdown

* Integrated directly into the Frappe HR PWA (`/hrms/home` & `CheckInPanel.vue`).
* Displays:
  * Current scheduled shift hours: `09:00 AM – 05:00 PM`.
  * Live second-by-second countdown to shift end (`15 minutes remaining` / `Xh Ym Zs`) computed locally without flooding the server.
  * Prominent amber alert banner when checkout is approaching: *"Your shift is ending soon. Please remember to check out."*
  * Dynamic Check Out button.
  * Scheduled start reminder when not checked in.

### 6. Atomic Idempotency & Concurrency Safety

* Every notification run generates a deterministic key:
  `{NOTIFICATION_TYPE}_{EMPLOYEE}_{SHIFT_ASSIGNMENT}_{YYYYMMDDHHMM}`.
* Backed by database uniqueness constraint in `Shift Notification Log` to guarantee zero duplicate messages across multi-worker bench schedulers.

---

## Architecture & File Structure

```text
apps/shift_notifications/
├── README.md
├── shift_notifications/
│   ├── hooks.py                             # Scheduler (1-min cron) & App configuration
│   ├── modules.txt
│   ├── doctype/
│   │   ├── shift_notification_settings/     # Single DocType for global configurations
│   │   │   ├── shift_notification_settings.json
│   │   │   └── shift_notification_settings.py
│   │   └── shift_notification_log/          # Audit log & idempotency tracking
│   │       ├── shift_notification_log.json
│   │       └── shift_notification_log.py
│   ├── services/
│   │   ├── shift_service.py                 # Shift window resolution & overnight math
│   │   ├── attendance_service.py            # Punches, leave, & holiday checks
│   │   ├── notification_service.py          # Atomic idempotency, PWA Push & Desk alerts
│   │   └── shift_evaluator.py               # Evaluation engine for the 4 notification rules
│   ├── tasks/
│   │   └── check_shift_reminders.py         # Scheduler tasks & log retention cleanup
│   ├── api/
│   │   └── employee_shift.py                # Whitelisted API: get_my_shift_status
│   └── tests/
│       └── test_shift_notifications.py      # Automated test suite
```

---

## Installation & Setup

### 1. Install to Bench Site

```bash
cd /home/lenovo/frappe15-new-bench

# Install app to shift.com site
bench --site shift.com install-app shift_notifications

# Run migrations to register DocTypes
bench --site shift.com migrate
```

### 2. Configure Settings

In Frappe Desk, navigate to:
**Awesome Bar &rarr; Shift Notification Settings**

* **Enable Shift Notifications**: Ensure checked.
* **Notification Channel**: Choose `Push Notification`, `System Notification`, or `Both`.
* Adjust check-in and check-out reminder thresholds according to company policy.
* Save the document.

### 3. Run Automated Tests

```bash
bench --site shift.com run-tests --app shift_notifications
```
