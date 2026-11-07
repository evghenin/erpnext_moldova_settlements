# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def before_cancel(doc, method=None):
	register = doc.get("settlement_register")
	if not register or frappe.db.get_value("Settlement Register", register, "docstatus") != 1:
		return
	from erpnext_moldova_settlements.moldova_settlements.register import release_journal_links

	release_journal_links(register, doc.name)


def ensure_settlement_register_field():
	if frappe.get_meta("Journal Entry").has_field("settlement_register"):
		return
	create_custom_fields(
		{
			"Journal Entry": [
				{
					"fieldname": "settlement_register",
					"label": "Settlement Register",
					"fieldtype": "Link",
					"options": "Settlement Register",
					"insert_after": "cheque_no",
					"read_only": 1,
					"hidden": 1,
					"no_copy": 1,
					"allow_on_submit": 1,
				}
			]
		},
		update=True,
	)


def get_dashboard_data(data):
	data = frappe._dict(data)
	data.setdefault("transactions", [])
	data.setdefault("internal_links", {})
	data.internal_links["Settlement Register"] = "settlement_register"
	if not any("Settlement Register" in (group.get("items") or []) for group in data.transactions):
		group = data.transactions[0] if data.transactions else {"items": []}
		group.setdefault("items", []).append("Settlement Register")
		if group not in data.transactions:
			data.transactions.append(group)
	if not data.fieldname:
		data.fieldname = "journal_entry"
	return data
