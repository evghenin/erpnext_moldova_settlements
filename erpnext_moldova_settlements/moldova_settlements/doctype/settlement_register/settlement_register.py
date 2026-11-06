# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_moldova_settlements.moldova_settlements.register import (
	before_cancel_register,
	before_submit_register,
	create_payment_entries,
	fill_fee_debits,
	fill_deposit_transactions,
	fill_payment_documents,
	read_source_file,
	refresh_submitted_register,
	validate_register,
)


class SettlementRegister(Document):
	def before_naming(self):
		read_source_file(self)

	def validate(self):
		if self.is_new() and self.source_file and not self.payments:
			read_source_file(self)
		validate_register(self)

	def before_submit(self):
		before_submit_register(self)

	def before_cancel(self):
		before_cancel_register(self)

	def before_update_after_submit(self):
		refresh_submitted_register(self)


def _open(name):
	doc = frappe.get_doc("Settlement Register", name)
	doc.check_permission("write")
	if doc.docstatus == 2:
		frappe.throw(_("A cancelled register cannot be changed."))
	return doc


@frappe.whitelist()
def identify_payments(name):
	doc = _open(name)
	fill_payment_documents(doc)
	doc.save()


@frappe.whitelist()
def identify_fee_debits(name):
	doc = _open(name)
	fill_fee_debits(doc)
	doc.save()


@frappe.whitelist()
def identify_deposits(name):
	doc = _open(name)
	fill_deposit_transactions(doc)
	doc.save()


@frappe.whitelist()
def create_missing_payments(name):
	doc = _open(name)
	create_payment_entries(doc)
	doc.save()
