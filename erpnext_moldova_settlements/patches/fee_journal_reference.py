# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe

from erpnext_moldova_settlements.moldova_settlements.register import backfill_fee_links


def execute():
	if not frappe.db.table_exists("Settlement Register Fee"):
		return
	backfill_fee_links()
