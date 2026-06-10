app_name = "harness"
app_title = "Harness"
app_publisher = "koyabank"
app_description = "Harness app"
app_email = "admin@koyabank.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Desk app identity — the /apps launcher tile + the app switcher. Mirrors the Frappe CRM
# pattern (crm/hooks.py:7-23). Assets live in harness/public/images/ (served at /assets/harness/).
# Routes point at the DESK landing page (Phase-3 Operations Console), never an SPA — the harness
# is a desk app.
app_icon_url = "/assets/harness/images/logo.png"
app_icon_title = "Koya Harness"
app_icon_route = "/app/koya-harness-home"

# Shown on the /apps launcher, gated by has_permission (harness roles only).
add_to_apps_screen = [
	{
		"name": "harness",
		"logo": "/assets/harness/images/logo.png",
		"title": "Koya Harness",
		"route": "/app/koya-harness-home",
		"has_permission": "harness.api.permission.check_app_permission",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/harness/css/harness.css"
# app_include_js = "/assets/harness/js/harness.js"

# include js, css files in header of web template
# web_include_css = "/assets/harness/css/harness.css"
# web_include_js = "/assets/harness/js/harness.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "harness/public/scss/website"

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
# app_include_icons = "harness/public/icons.svg"

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

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "harness.utils.jinja_methods",
# 	"filters": "harness.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "harness.install.before_install"
# after_install = "harness.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "harness.uninstall.before_uninstall"
# after_uninstall = "harness.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "harness.utils.before_app_install"
# after_app_install = "harness.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "harness.utils.before_app_uninstall"
# after_app_uninstall = "harness.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "harness.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "harness.notifications.get_notification_config"

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

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"harness.tasks.all"
# 	],
# 	"daily": [
# 		"harness.tasks.daily"
# 	],
# 	"hourly": [
# 		"harness.tasks.hourly"
# 	],
# 	"weekly": [
# 		"harness.tasks.weekly"
# 	],
# 	"monthly": [
# 		"harness.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "harness.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "harness.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "harness.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "harness.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["harness.utils.before_request"]
# kronos is an INTERNAL app — stamp X-Robots-Tag: noindex on EVERY response (site-wide,
# all apps' routes) so no crawler ever indexes it. Authoritative + code-side. See
# harness/api/noindex.py.
after_request = ["harness.api.noindex.set_no_index_headers"]

# Keep /robots.txt as Disallow-all (code-enforced on every migrate).
after_migrate = ["harness.api.noindex.enforce_robots_txt"]

# Job Events
# ----------
# before_job = ["harness.utils.before_job"]
# after_job = ["harness.utils.after_job"]

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
# 	"harness.auth.validate"
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
