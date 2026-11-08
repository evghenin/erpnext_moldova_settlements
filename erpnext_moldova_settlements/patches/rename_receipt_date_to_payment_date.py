# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
	doctype = "Settlement Register Payment"
	if frappe.db.table_exists(doctype) and frappe.db.has_column(doctype, "receipt_date"):
		rename_field(doctype, "receipt_date", "payment_date")
