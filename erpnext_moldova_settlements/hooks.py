app_name = "erpnext_moldova_settlements"
app_title = "Moldova Settlements"
app_publisher = "Evgheni Nemerenco"
app_description = "Payment settlement registers for ERPNext v15: customer payments from Moldova payment systems, matched to clearing-account receipts."
app_email = "evgheni.nemerenco@gmail.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

inbound_email_handlers = [
	"erpnext_moldova_settlements.inbox.handle_inbound_email",
]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "erpnext_moldova_settlements",
# 		"logo": "/assets/erpnext_moldova_settlements/logo.png",
# 		"title": "Moldova Settlements",
# 		"route": "/erpnext_moldova_settlements",
# 		"has_permission": "erpnext_moldova_settlements.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/erpnext_moldova_settlements/css/erpnext_moldova_settlements.css"
# app_include_js = "/assets/erpnext_moldova_settlements/js/erpnext_moldova_settlements.js"

# include js, css files in header of web template
# web_include_css = "/assets/erpnext_moldova_settlements/css/erpnext_moldova_settlements.css"
# web_include_js = "/assets/erpnext_moldova_settlements/js/erpnext_moldova_settlements.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "erpnext_moldova_settlements/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "erpnext_moldova_settlements/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "erpnext_moldova_settlements.utils.jinja_methods",
# 	"filters": "erpnext_moldova_settlements.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "erpnext_moldova_settlements.install.before_install"
# after_install = "erpnext_moldova_settlements.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "erpnext_moldova_settlements.uninstall.before_uninstall"
# after_uninstall = "erpnext_moldova_settlements.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "erpnext_moldova_settlements.utils.before_app_install"
# after_app_install = "erpnext_moldova_settlements.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "erpnext_moldova_settlements.utils.before_app_uninstall"
# after_app_uninstall = "erpnext_moldova_settlements.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "erpnext_moldova_settlements.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

after_migrate = [
	"erpnext_moldova_settlements.moldova_settlements.journal_entry.ensure_settlement_register_field",
	"erpnext_moldova_settlements.moldova_settlements.workspace.ensure_accounting_shortcut",
]

override_doctype_dashboards = {
	"Journal Entry": "erpnext_moldova_settlements.moldova_settlements.journal_entry.get_dashboard_data"
}

doc_events = {
	"Bank Transaction": {
		"on_update": "erpnext_moldova_settlements.moldova_settlements.register.refresh_registers_for_bank_transaction",
		"on_update_after_submit": "erpnext_moldova_settlements.moldova_settlements.register.refresh_registers_for_bank_transaction",
	}
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"erpnext_moldova_settlements.tasks.all"
# 	],
# 	"daily": [
# 		"erpnext_moldova_settlements.tasks.daily"
# 	],
# 	"hourly": [
# 		"erpnext_moldova_settlements.tasks.hourly"
# 	],
# 	"weekly": [
# 		"erpnext_moldova_settlements.tasks.weekly"
# 	],
# 	"monthly": [
# 		"erpnext_moldova_settlements.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "erpnext_moldova_settlements.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "erpnext_moldova_settlements.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "erpnext_moldova_settlements.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["erpnext_moldova_settlements.utils.before_request"]
# after_request = ["erpnext_moldova_settlements.utils.after_request"]

# Job Events
# ----------
# before_job = ["erpnext_moldova_settlements.utils.before_job"]
# after_job = ["erpnext_moldova_settlements.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"erpnext_moldova_settlements.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

