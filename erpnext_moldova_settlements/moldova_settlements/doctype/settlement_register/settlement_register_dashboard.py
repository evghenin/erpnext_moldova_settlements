# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe


def get_data():
	transactions = [
		{"label": "Accounting", "items": ["Journal Entry", "Payment Entry", "Bank Transaction", "Sales Invoice"]}
	]
	internal_links = {
		"Journal Entry": ["reference_rows", "journal_entry"],
		"Payment Entry": ["reference_rows", "payment_entry"],
		"Bank Transaction": ["reference_rows", "bank_transaction"],
		"Sales Invoice": ["reference_rows", "sales_invoice"],
	}
	if frappe.db.exists("DocType", "Supplier Inbox Email"):
		transactions.append({"label": "Inbox", "items": ["Supplier Inbox Email"]})
		internal_links["Supplier Inbox Email"] = "supplier_inbox_email"
	return {
		"fieldname": "settlement_register",
		"transactions": transactions,
		"internal_links": internal_links,
	}
