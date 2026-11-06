# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SettlementsSettings(Document):
	def validate(self):
		seen = set()
		for row in self.sources:
			key = (row.company, row.source)
			if key in seen:
				frappe.throw(_("Company {0} already has a row for {1}.").format(row.company, row.source))
			seen.add(key)
			if row.bank_account and frappe.db.get_value("Bank Account", row.bank_account, "company") != row.company:
				frappe.throw(_("The bank account belongs to another company."))
			for account in (row.clearing_account, row.fee_account):
				if account and frappe.db.get_value("Account", account, "company") != row.company:
					frappe.throw(_("The account {0} belongs to another company.").format(account))
