# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_moldova_settlements.inbox import release_inbox_handler
from erpnext_moldova_settlements.moldova_settlements.register import (
	before_cancel_register,
	before_submit_register,
	commission_invoice_query as search_commission_invoices,
	create_payment_entries,
	fill_fee_debits,
	fill_deposit_transactions,
	fill_payment_documents,
	find_fee_invoices,
	read_source_file,
	refresh_submitted_register,
	release_journal_register_link,
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

	def on_cancel(self):
		release_inbox_handler(self.name, clear_reference=False)

	def on_trash(self):
		release_inbox_handler(self.name, clear_reference=True)
		release_journal_register_link(self.name)

	def before_update_after_submit(self):
		refresh_submitted_register(self)


def _open(name):
	doc = frappe.get_doc("Settlement Register", name)
	doc.check_permission("write")
	if doc.docstatus == 2:
		frappe.throw(_("A cancelled register cannot be changed."))
	return doc


def _form_doc(payload):
	if isinstance(payload, str):
		payload = frappe.parse_json(payload)
	if not isinstance(payload, dict) or payload.get("doctype") != "Settlement Register":
		frappe.throw(_("A settlement register is required."))
	doc = frappe.get_doc(payload)
	if doc.name and frappe.db.exists("Settlement Register", doc.name):
		doc.check_permission("write")
		if frappe.db.get_value("Settlement Register", doc.name, "docstatus") == 2:
			frappe.throw(_("A cancelled register cannot be changed."))
	else:
		frappe.has_permission("Settlement Register", "create", throw=True)
	if doc.docstatus == 2:
		frappe.throw(_("A cancelled register cannot be changed."))
	return doc


def _identified(doc, fee_debits=None):
	return {
		"payments": [
			{
				"name": row.name,
				"payment_entry": row.payment_entry,
				"sales_invoice": row.sales_invoice,
				"customer": row.customer,
				"row_bullet": row.row_bullet,
			}
			for row in doc.payments
		],
		"deposits": [
			{
				"name": row.name,
				"bank_transaction": row.bank_transaction,
				"payment_entry": row.payment_entry,
				"journal_entry": row.journal_entry,
				"row_bullet": row.row_bullet,
			}
			for row in doc.deposits
		],
		"fees": [
			{
				"name": row.name,
				"row_bullet": row.row_bullet,
				"journal_entry": row.journal_entry,
				"purchase_invoice": row.purchase_invoice,
			}
			for row in doc.fees
		],
		"fee_debits": fee_debits or [],
	}


@frappe.whitelist()
def identify_payments(doc):
	doc = _form_doc(doc)
	fill_payment_documents(doc)
	return _identified(doc)


@frappe.whitelist()
def identify_fee_debits(doc):
	doc = _form_doc(doc)
	before = {row.name for row in doc.fee_debits}
	fill_fee_debits(doc)
	added = [
		{
			"settlement_register_fee": row.settlement_register_fee,
			"amount": row.amount,
			"bank_transaction": row.bank_transaction,
			"journal_entry": row.journal_entry,
			"currency": row.currency,
		}
		for row in doc.fee_debits
		if row.name not in before
	]
	return _identified(doc, added)


@frappe.whitelist()
def commission_invoice_query(doctype, txt, searchfield, start, page_len, filters):
	return search_commission_invoices(doctype, txt, searchfield, start, page_len, filters)


@frappe.whitelist()
def identify_fee_invoices(doc):
	doc = _form_doc(doc)
	find_fee_invoices(doc)
	return _identified(doc)


@frappe.whitelist()
def identify_deposits(doc):
	doc = _form_doc(doc)
	fill_deposit_transactions(doc)
	return _identified(doc)


@frappe.whitelist()
def create_missing_payments(name):
	doc = _open(name)
	create_payment_entries(doc)
	doc.save()
