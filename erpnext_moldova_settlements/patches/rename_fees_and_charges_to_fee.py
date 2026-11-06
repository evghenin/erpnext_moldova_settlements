# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe
from frappe.model.rename_doc import rename_doc


def execute():
	_parentfield("Settlement Register Commission", "fees", ("commissions", "fees_and_charges"))
	_parentfield("Settlement Register Fees and Charges", "fees", ("commissions", "fees_and_charges"))
	_parentfield("Settlement Register Fee", "fees", ("commissions", "fees_and_charges"))
	_parentfield("Settlement Register Commission Debit", "fee_debits", ("commission_debits",))
	_parentfield("Settlement Register Fee Debit", "fee_debits", ("commission_debits",))
	_rename_doctype("Settlement Register Fees and Charges", "Settlement Register Fee")
	_rename_doctype("Settlement Register Commission", "Settlement Register Fee")
	_rename_doctype("Settlement Register Commission Debit", "Settlement Register Fee Debit")


def _parentfield(doctype, new, old_values):
	if not frappe.db.table_exists(doctype):
		return
	placeholders = ", ".join(["%s"] * len(old_values))
	frappe.db.sql(
		f"update `tab{doctype}` set parentfield = %s where parentfield in ({placeholders})",
		(new, *old_values),
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
