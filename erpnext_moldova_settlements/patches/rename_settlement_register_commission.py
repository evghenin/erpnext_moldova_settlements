# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe
from frappe.model.rename_doc import rename_doc


def execute():
	old = "Settlement Register Commission"
	new = "Settlement Register Fees and Charges"
	if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
		rename_doc(
			"DocType",
			old,
			new,
			force=True,
			ignore_permissions=True,
			show_alert=False,
			rebuild_search=False,
		)
