# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
	for doctype in ("Settlement Register", "Settlements Source"):
		if frappe.db.table_exists(doctype) and frappe.db.has_column(doctype, "card_mode_of_payment"):
			rename_field(doctype, "card_mode_of_payment", "mode_of_payment")
