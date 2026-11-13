# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def get_dashboard_data(data):
	data = frappe._dict(data)
	data.setdefault("transactions", [])
	payment = None
	for group in data.transactions:
		if "Payment Entry" in (group.get("items") or []):
			payment = group
			break
	if payment is None:
		payment = {"label": _("Payment"), "items": []}
		data.transactions.insert(0, payment)
	items = payment.setdefault("items", [])
	if "Settlement Register" not in items:
		items.append("Settlement Register")
	return data
