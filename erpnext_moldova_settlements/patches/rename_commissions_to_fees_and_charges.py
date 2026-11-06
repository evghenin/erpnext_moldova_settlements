# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe


def execute():
	if not frappe.db.table_exists("Settlement Register Commission"):
		return
	frappe.db.sql(
		"""update `tabSettlement Register Commission`
		set parentfield = %s
		where parenttype = 'Settlement Register' and parentfield = %s""",
		("fees_and_charges", "commissions"),
	)
