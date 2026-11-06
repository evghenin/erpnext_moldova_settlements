# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe
from frappe.model.rename_doc import rename_doc


def execute():
	_rename_doctype("Moldova Settlements Source", "Settlements Source")
	_rename_doctype("Moldova Settlements Settings", "Settlements Settings")
	if frappe.db.table_exists("Settlements Source"):
		frappe.db.sql(
			"update `tabSettlements Source` set parent = %s where parent = %s",
			("Settlements Settings", "Moldova Settlements Settings"),
		)


def _rename_doctype(old, new):
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
