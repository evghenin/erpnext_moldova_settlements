# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe


def execute():
	for table in ("Settlement Register", "Settlements Source"):
		if frappe.db.table_exists(table):
			frappe.db.sql(
				f"update `tab{table}` set source = %s where source = %s",
				("MAIB POS", "Acquirer"),
			)
