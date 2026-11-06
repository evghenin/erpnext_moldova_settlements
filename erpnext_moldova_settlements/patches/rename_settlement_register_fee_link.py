# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
	for doctype in ("Settlement Register Payment", "Settlement Register Fee Debit"):
		if frappe.db.table_exists(doctype) and frappe.db.has_column(doctype, "settlement_register_commission"):
			rename_field(doctype, "settlement_register_commission", "settlement_register_fee")
