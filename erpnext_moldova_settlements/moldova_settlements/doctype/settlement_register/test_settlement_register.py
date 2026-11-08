# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.file_manager import save_file

from erpnext_moldova_settlements.moldova_settlements.parsers.register_file import DEPOSIT_PATTERNS
from erpnext_moldova_settlements.moldova_settlements.doctype.settlement_register.settlement_register import (
	identify_payments,
)
from erpnext_moldova_settlements.moldova_settlements.register import (
	_invoice_reference_field,
	create_payment_entries,
	fill_deposit_transactions,
	fill_fee_debits,
	fill_payment_documents,
)

EXAMPLES = Path(__file__).resolve().parents[3] / "examples"
COMPANY = "_Settlements Co"
test_ignore = [
	"Account",
	"Bank Account",
	"Bank Transaction",
	"Company",
	"Currency",
	"Customer",
	"Journal Entry",
	"Mode of Payment",
	"Payment Entry",
	"Sales Invoice",
	"Supplier",
	"Settlement Register",
	"Settlement Register Deposit",
	"Settlement Register Fee",
]


class TestSettlementRegister(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		_ensure_currency()
		_ensure_company()
		cls.clearing = _ledger(COMPANY, "Asset", "_Settlements Clearing", "Bank")
		cls.other_bank = _ledger(COMPANY, "Asset", "_Settlements Other Bank", "Bank")
		cls.fee = _ledger(COMPANY, "Expense", "_Settlements Fee")
		cls.income = _ledger(COMPANY, "Income", "_Settlements Income", "Income Account")
		cls.customer = _customer("_Settlements Customer")
		cls.other_customer = _customer("_Settlements Other Customer")
		cls.supplier = _supplier("_Settlements Payer")
		cls.other_supplier = _supplier("_Settlements Other Payer")
		cls.mode = _mode_of_payment(cls.clearing)
		cls.bank_account = _bank_account(cls.clearing)
		cls.item = _item()
		_fiscal_year()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._settings(create_payment_if_missing=1, search_payments=1)

	def test_same_file_does_not_create_a_second_register(self):
		first = self.from_file("novapay", "Реестр платежей №00000015836.XLSX")
		self.assertEqual(first.register_number, "NP-00000015836")
		self.assertTrue(first.name.startswith("STR-"))
		self.assertEqual(len(first.payments), 1)
		second = frappe.new_doc("Settlement Register")
		second.source_file = first.source_file
		second.company = COMPANY
		self.assertRaises(frappe.ValidationError, second.insert)
		self.assertEqual(
			frappe.db.count(
				"Settlement Register",
				{"register_number": "NP-00000015836", "docstatus": ["<", 2]},
			),
			1,
		)

	def test_file_amounts_are_stored_as_read(self):
		doc = self.from_file("novapay", "Реестр платежей №00000008204.XLSX")
		row = doc.payments[0]
		self.assertEqual(round(row.payment_amount, 2), 2213)
		self.assertEqual(round(row.fee_amount, 2), 55.33)
		self.assertEqual(round(row.net_amount, 2), 2157.67)
		self.assertEqual(len(doc.fees), 1)
		self.assertEqual(round(doc.fees[0].fee_amount, 2), 55.33)
		self.assertEqual(round(doc.deposits[0].transfer_amount, 2), 2157.67)

		mega = self.from_file("megamega", "Реестр платежей.XLSX")
		self.assertEqual(len(mega.fees), 1)
		self.assertEqual(round(mega.payments[0].fee_amount, 2), 127.97)
		self.assertEqual(round(mega.payments[0].net_amount, 2), 560.03)
		self.assertEqual(round(mega.deposits[0].transfer_amount, 2), 560.03)

	def test_submit_posts_one_fee_journal_and_no_payment(self):
		doc = self.from_file("novapay", "Реестр платежей №00000016330.XLSX")
		payment = self.payment(doc.payments[0].payment_amount)
		doc.submit()
		doc.reload()
		self.assertEqual(doc.status, "Unreconciled")
		self.assertFalse(doc.payments[0].payment_entry)
		self.assertEqual(len(doc.fees), 1)
		self.assertTrue(doc.fees[0].journal_entry)
		self.assertEqual(doc.fees[0].journal_created, 1)
		journal = frappe.get_doc("Journal Entry", doc.fees[0].journal_entry)
		self.assertFalse(journal.cheque_no)
		self.assertEqual(journal.docstatus, 1)
		self.assertEqual(
			frappe.db.count("Journal Entry", {"settlement_register": doc.name, "docstatus": 1}),
			1,
		)
		self.assertEqual(frappe.db.get_value("Payment Entry", payment, "docstatus"), 1)

	def test_cancelled_register_can_be_imported_again(self):
		doc = self.from_file("novapay", "Реестр платежей №00000012315.XLSX")
		doc.submit()
		journal = doc.fees[0].journal_entry
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", journal, "docstatus"), 2)
		again = self.from_file("novapay", "Реестр платежей №00000012315.XLSX")
		self.assertEqual(again.register_number, "NP-00000012315")
		self.assertEqual(doc.register_number, "NP-00000012315")
		self.assertNotEqual(again.name, doc.name)
		self.assertTrue(again.name.startswith("STR-"))
		self.assertEqual(again.docstatus, 0)
		self.assertEqual(doc.docstatus, 2)
		third = frappe.new_doc("Settlement Register")
		third.source_file = again.source_file
		third.company = COMPANY
		self.assertRaises(frappe.ValidationError, third.insert)

	def test_deleted_draft_is_replaced_when_the_inbox_handler_runs_again(self):
		mail = self._inbox_with_register_file("novapay", "Реестр платежей №00000008204.XLSX")
		first = self._run_inbox_handler(mail)
		self.assertEqual(frappe.db.get_value("Settlement Register", first, "docstatus"), 0)
		frappe.delete_doc("Settlement Register", first)
		self.assertFalse(frappe.db.exists("Settlement Register", first))
		queued = self._inbox_handler_row(mail)
		self.assertEqual(queued.status, "Queued")
		self.assertFalse(queued.reference_name)
		second = self._run_inbox_handler(mail)
		self.assertEqual(frappe.db.get_value("Settlement Register", second, "docstatus"), 0)
		self.assertEqual(frappe.db.get_value("Settlement Register", second, "supplier_inbox_email"), mail)
		row = self._inbox_handler_row(mail)
		self.assertEqual(row.status, "Processed")
		self.assertEqual(row.reference_doctype, "Settlement Register")
		self.assertEqual(row.reference_name, second)

	def test_cancelled_register_is_replaced_when_the_inbox_handler_runs_again(self):
		mail = self._inbox_with_register_file("novapay", "Реестр платежей №00000016330.XLSX")
		first = self._run_inbox_handler(mail)
		frappe.get_doc("Settlement Register", first).submit()
		frappe.get_doc("Settlement Register", first).cancel()
		self.assertEqual(frappe.db.get_value("Settlement Register", first, "docstatus"), 2)
		queued = self._inbox_handler_row(mail)
		self.assertEqual(queued.status, "Queued")
		self.assertEqual(queued.reference_name, first)
		second = self._run_inbox_handler(mail)
		self.assertNotEqual(second, first)
		self.assertEqual(frappe.db.get_value("Settlement Register", second, "docstatus"), 0)
		self.assertEqual(frappe.db.get_value("Settlement Register", second, "supplier_inbox_email"), mail)
		row = self._inbox_handler_row(mail)
		self.assertEqual(row.status, "Processed")
		self.assertEqual(row.reference_name, second)

	def test_journal_entry_can_be_cancelled_while_the_register_points_at_it(self):
		from frappe.desk.form.linked_with import get_submitted_linked_docs

		doc = self.from_file("novapay", "Реестр платежей №00000015659.XLSX")
		doc.submit()
		journal = doc.fees[0].journal_entry
		linked = get_submitted_linked_docs("Settlement Register", doc.name)["docs"]
		self.assertIn({"doctype": "Journal Entry", "name": journal, "docstatus": 1}, linked)
		ignored = get_submitted_linked_docs(
			"Settlement Register", doc.name, ["Journal Entry", "Payment Entry"]
		)["docs"]
		self.assertFalse(any(row["doctype"] == "Journal Entry" for row in ignored))
		frappe.get_doc("Journal Entry", journal).cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", journal, "docstatus"), 2)
		self.assertFalse(frappe.db.get_value("Settlement Register Fee", {"parent": doc.name}, "journal_entry"))
		doc.reload()
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.status, "Unreconciled")
		self.assertFalse(doc.fees[0].journal_entry)
		self.assertEqual(doc.fees[0].journal_created, 0)
		doc.cancel()
		self.assertEqual(doc.docstatus, 2)

	def test_manual_payment_link_must_match_amount_account_and_currency(self):
		doc = self.register(
			"NovaPay",
			"NP-manual-amount",
			[self.row(100, 3, 97, "SHMD-AMOUNT")],
		)
		wrong_amount = self.payment(90)
		doc.payments[0].payment_entry = wrong_amount
		self.assertRaises(frappe.ValidationError, doc.save)
		self.assertRaises(frappe.ValidationError, doc.submit)

		doc = self.register(
			"NovaPay",
			"NP-manual-account",
			[self.row(100, 3, 97, "SHMD-ACCOUNT")],
		)
		wrong_account = self.payment(100, paid_to=self.other_bank)
		doc.payments[0].payment_entry = wrong_account
		self.assertRaises(frappe.ValidationError, doc.save)

		doc = self.register(
			"NovaPay",
			"NP-manual-currency",
			[self.row(100, 3, 97, "SHMD-CURRENCY")],
		)
		other_currency = self.payment(100)
		frappe.db.set_value("Payment Entry", other_currency, "paid_to_account_currency", "USD")
		doc.payments[0].payment_entry = other_currency
		self.assertRaises(frappe.ValidationError, doc.save)

		doc = self.register(
			"NovaPay",
			"NP-manual-ok",
			[self.row(100, 3, 97, "SHMD-OK")],
		)
		doc.payments[0].payment_entry = self.payment(100)
		doc.save()
		self.assertEqual(doc.payments[0].customer, self.customer)

	def test_manual_invoice_link_must_match_amount_and_clearing_account(self):
		invoice = self.pos_invoice(100)
		doc = self.register(
			"MAIB POS",
			"MAIB-manual-invoice",
			[self.row(80, 2, 78, "RRN-WRONG")],
		)
		doc.payments[0].sales_invoice = invoice
		self.assertRaises(frappe.ValidationError, doc.save)

		doc = self.register(
			"MAIB POS",
			"MAIB-manual-invoice-ok",
			[self.row(100, 2.5, 97.5, "RRN-OK")],
		)
		doc.payments[0].sales_invoice = invoice
		doc.save()
		self.assertEqual(doc.payments[0].sales_invoice, invoice)

	def test_search_fills_an_empty_row_and_keeps_a_manual_link(self):
		kept = self.payment(100)
		self.payment(100)
		doc = self.register(
			"NovaPay",
			"NP-search",
			[
				self.row(100, 3, 97, "SHMD-KEPT", customer=self.customer),
				self.row(40, 1, 39, "SHMD-EMPTY"),
			],
		)
		doc.payments[0].payment_entry = kept
		self.payment(40)
		fill_payment_documents(doc)
		self.assertEqual(doc.payments[0].payment_entry, kept)
		self.assertEqual(doc.payments[0].customer, self.customer)
		self.assertTrue(doc.payments[1].payment_entry)
		self.assertNotEqual(doc.payments[1].payment_entry, kept)
		self.assertEqual(doc.payments[1].customer, self.customer)

	def test_identify_payments_fills_the_response_and_leaves_the_register(self):
		self._settings(create_payment_if_missing=1, search_payments=1)
		self.payment(40)
		doc = self.register(
			"NovaPay",
			"NP-identify-form",
			[self.row(40, 1, 39, "SHMD-FORM")],
		)
		modified = frappe.db.get_value("Settlement Register", doc.name, "modified")
		result = identify_payments(doc.as_dict())
		doc.reload()
		self.assertFalse(doc.payments[0].payment_entry)
		self.assertEqual(frappe.db.get_value("Settlement Register", doc.name, "modified"), modified)
		self.assertEqual(result["payments"][0]["name"], doc.payments[0].name)
		self.assertTrue(result["payments"][0]["payment_entry"])
		self.assertEqual(result["payments"][0]["customer"], self.customer)

	def test_selected_customer_is_not_replaced(self):
		self.payment(100)
		doc = self.register(
			"NovaPay",
			"NP-customer",
			[self.row(100, 3, 97, "SHMD-OTHER", customer=self.other_customer)],
		)
		fill_payment_documents(doc)
		self.assertEqual(doc.payments[0].customer, self.other_customer)
		self.assertFalse(doc.payments[0].payment_entry)

	def test_register_submits_without_a_customer(self):
		self._settings(create_payment_if_missing=1, search_payments=1)
		settings = frappe.get_single("Settlements Settings")
		for row in settings.sources:
			if row.company == COMPANY and row.source == "NovaPay":
				row.default_customer = None
		settings.save()
		doc = self.register(
			"NovaPay",
			"NP-no-customer",
			[self.row(100, 3, 97, "SHMD-NOCUST")],
		)
		self.assertFalse(doc.payments[0].customer)
		doc.submit()
		doc.reload()
		self.assertEqual(doc.docstatus, 1)
		self.assertFalse(doc.payments[0].customer)
		self.assertEqual(doc.status, "Unreconciled")
		self.assertTrue(doc.fees[0].journal_entry)

	def test_customer_can_be_changed_after_submit(self):
		doc = self.register(
			"NovaPay",
			"NP-change-customer",
			[self.row(100, 3, 97, "SHMD-CHANGE")],
		)
		doc.submit()
		doc.reload()
		self.assertEqual(doc.payments[0].customer, self.customer)
		doc.payments[0].customer = self.other_customer
		doc.save()
		doc.reload()
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.payments[0].customer, self.other_customer)
		self.assertFalse(doc.payments[0].payment_entry)

	def test_cancelling_a_created_payment_leaves_the_register_submitted(self):
		doc = self.register(
			"NovaPay",
			"NP-cancel-payment",
			[self.row(100, 3, 97, "SHMD-CANCEL-PE")],
		)
		doc.submit()
		create_payment_entries(doc)
		doc.save()
		doc.reload()
		payment = doc.payments[0].payment_entry
		bank_transaction = self.bank_transaction(
			deposit=97,
			description="PLATA PENTRU RAMBURS",
			supplier=self.supplier,
		)
		frappe.db.set_value("Bank Transaction", bank_transaction, "status", "Reconciled")
		doc.deposits[0].bank_transaction = bank_transaction
		doc.save()
		doc.reload()
		self.assertEqual(doc.status, "Reconciled")
		frappe.get_doc("Payment Entry", payment).cancel()
		self.assertEqual(frappe.db.get_value("Payment Entry", payment, "docstatus"), 2)
		doc.reload()
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.status, "Unreconciled")
		self.assertFalse(doc.payments[0].payment_entry)
		self.assertEqual(doc.payments[0].payment_created, 0)
		self.assertFalse(any(row.payment_entry == payment for row in doc.reference_rows))
		self.assertTrue(doc.fees[0].journal_entry)

	def test_submit_does_not_search_or_create_a_payment(self):
		doc = self.register(
			"NovaPay",
			"NP-no-search",
			[self.row(100, 3, 97, "SHMD-NOSRCH")],
		)
		self.payment(100)
		doc.submit()
		doc.reload()
		self.assertFalse(doc.payments[0].payment_entry)
		self.assertEqual(doc.status, "Unreconciled")
		self.assertEqual(frappe.db.count("Payment Entry", {"reference_no": "SHMD-NOSRCH"}), 0)

	def test_create_payment_uses_the_row_amount_and_mode(self):
		doc = self.register(
			"NovaPay",
			"NP-create",
			[self.row(100, 3, 97, "SHMD-CREATE")],
		)
		doc.submit()
		create_payment_entries(doc)
		doc.save()
		doc.reload()
		payment = frappe.get_doc("Payment Entry", doc.payments[0].payment_entry)
		self.assertEqual(payment.paid_amount, 100)
		self.assertEqual(payment.paid_to, self.clearing)
		self.assertEqual(payment.mode_of_payment, self.mode)
		self.assertEqual(payment.party, self.customer)
		self.assertEqual(doc.payments[0].payment_created, 1)
		create_payment_entries(doc)
		doc.save()
		self.assertEqual(frappe.db.count("Payment Entry", {"reference_no": "SHMD-CREATE"}), 1)

	def test_found_payment_is_not_created_again(self):
		doc = self.register(
			"NovaPay",
			"NP-found",
			[self.row(100, 3, 97, "SHMD-FOUND")],
		)
		existing = self.payment(100)
		doc.payments[0].payment_entry = existing
		doc.submit()
		create_payment_entries(doc)
		doc.save()
		self.assertEqual(doc.payments[0].payment_entry, existing)
		self.assertEqual(doc.payments[0].payment_created, 0)

	def test_disabled_creation_leaves_the_register_unreconciled(self):
		self._settings(create_payment_if_missing=0, search_payments=1)
		doc = self.register(
			"NovaPay",
			"NP-nocreate",
			[self.row(100, 3, 97, "SHMD-NOCREATE")],
		)
		doc.submit()
		doc.reload()
		self.assertEqual(doc.status, "Unreconciled")
		self.assertFalse(doc.payments[0].payment_entry)
		self.assertRaises(frappe.ValidationError, lambda: create_payment_entries(doc))

	def test_maib_pos_groups_by_transfer_date_and_posts_no_fee_journal(self):
		doc = self.from_file("maib pos", "aDetailPayRep_lunar_decontat20261002_HOTEL LIFE SRL SmartPOS.xlsx")
		self.assertEqual(len(doc.fees), 27)
		self.assertEqual(len(doc.deposits), 27)
		self.assertEqual(round(sum(row.transfer_amount for row in doc.deposits), 2), 105767.70)
		self.assertEqual(round(sum(row.fee_amount for row in doc.fees), 2), 1422.31)
		doc.submit()
		doc.reload()
		self.assertEqual(doc.status, "Unreconciled")
		self.assertTrue(all(not row.journal_entry for row in doc.fees))
		self.assertFalse(frappe.db.exists("Journal Entry", {"settlement_register": doc.name}))

	def test_maib_ecomm_posts_one_fee_journal_without_a_reference_number(self):
		doc = self.from_file("maib pos", "aDetailPayEcommRep_decontat20260909_Ecomm HOTEL LIFE S.R.L.xlsx")
		self.assertEqual(round(doc.deposits[0].transfer_amount, 2), 1880.80)
		doc.submit()
		doc.reload()
		journal = frappe.get_doc("Journal Entry", doc.fees[0].journal_entry)
		self.assertFalse(journal.cheque_no)
		fee_debit = [row.debit_in_account_currency for row in journal.accounts if row.account == self.fee]
		self.assertEqual([round(amount, 2) for amount in fee_debit], [59.2])

	def test_novapay_deposit_search_links_the_net_payout(self):
		doc = self.register(
			"NovaPay",
			"NP-payout",
			[self.row(100, 3, 97, "SHMD-PAYOUT")],
		)
		description = (
			"PLATA PENTRU RAMBURS PRIMIT CONFORM CONTRACT NR 929 DIN 19.08.2024"
			"A. TO TAL 97 MDL, FARA TVA"
		)
		match = self.bank_transaction(deposit=97, description=description, supplier=self.supplier)
		self.bank_transaction(deposit=100, description=description, supplier=self.supplier)
		self.bank_transaction(deposit=97, description="Incasare din alta sursa", supplier=self.supplier)
		fill_deposit_transactions(doc)
		self.assertEqual(doc.deposits[0].bank_transaction, match)
		self.assertEqual(round(doc.deposits[0].transfer_amount, 2), 97)

	def test_novapay_deposit_search_does_not_replace_a_chosen_payout(self):
		doc = self.register(
			"NovaPay",
			"NP-kept-payout",
			[self.row(100, 3, 97, "SHMD-KEPT")],
		)
		chosen = self.bank_transaction(deposit=10, description="manual")
		doc.deposits[0].bank_transaction = chosen
		self.bank_transaction(
			deposit=97,
			description="PLATA PENTRU RAMBURS PRIMIT CONFORM CONTRACT NR 929",
			supplier=self.supplier,
		)
		fill_deposit_transactions(doc)
		self.assertEqual(doc.deposits[0].bank_transaction, chosen)

	def test_novapay_deposit_search_leaves_the_row_empty_when_two_payouts_match(self):
		doc = self.register(
			"NovaPay",
			"NP-two-payouts",
			[self.row(100, 3, 97, "SHMD-TWO")],
		)
		description = "PLATA PENTRU RAMBURS PRIMIT"
		self.bank_transaction(deposit=97, description=description, supplier=self.supplier)
		self.bank_transaction(deposit=97, description=description, supplier=self.supplier)
		fill_deposit_transactions(doc)
		self.assertFalse(doc.deposits[0].bank_transaction)

	def test_maib_ecomm_deposit_search_links_the_net_payout(self):
		doc = self.register(
			"MAIB Ecomm",
			"MAIB-E-payout",
			[self.row(100, 7.32, 92.68, "625107054986")],
		)
		description = (
			"Transfer pentru operatiuni de accep tare a cardurilor la plata Ecomm "
			"HO TEL LIFE S.R.L. ( MDL 92.68 )"
		)
		match = self.bank_transaction(deposit=92.68, description=description, supplier=self.supplier)
		self.bank_transaction(
			deposit=92.68,
			description="Transfer pentru operatiuni de acceptare a cardurilor",
			supplier=self.supplier,
		)
		fill_deposit_transactions(doc)
		self.assertEqual(doc.deposits[0].bank_transaction, match)
		self.assertEqual(round(doc.deposits[0].transfer_amount, 2), 92.68)

	def test_maib_pos_deposit_search_skips_an_ecomm_payout(self):
		doc = self.register(
			"MAIB POS",
			"MAIB-pos-not-ecomm",
			[self.row(92.68, 0, 92.68, "RRN-POS-NET")],
		)
		self.bank_transaction(
			deposit=92.68,
			description=(
				"Transfer pentru operatiuni de acceptare a cardurilor la plata Ecomm "
				"HOTEL LIFE S.R.L. ( MDL 92.68 )"
			),
			supplier=self.supplier,
		)
		match = self.bank_transaction(
			deposit=92.68,
			description="Transfer pentru operatiuni de acceptare a cardurilor",
			supplier=self.supplier,
		)
		fill_deposit_transactions(doc)
		self.assertEqual(doc.deposits[0].bank_transaction, match)

	def test_megamega_deposit_search_links_the_net_payout(self):
		doc = self.register(
			"MegaMega",
			"MM-payout",
			[self.row(100, 18.6, 81.4, "MM-1")],
		)
		match = self.bank_transaction(
			deposit=81.4,
			description="Conform contractul nr 15 din 01.09.2026",
			supplier=self.supplier,
		)
		self.bank_transaction(
			deposit=81.4,
			description="Conform contractul nr 15 din 01.09.2026",
			supplier=self.other_supplier,
		)
		fill_deposit_transactions(doc)
		self.assertEqual(doc.deposits[0].bank_transaction, match)

	def test_fee_debit_search_adds_missing_rows_and_keeps_existing_ones(self):
		doc = self.register(
			"MAIB POS",
			"MAIB-debits",
			[self.row(100, 3, 97, "RRN-DEBIT")],
		)
		description = "Retinerea comisionului-operatiunile acceptare card"
		first = self.bank_transaction(withdrawal=1, description=description, supplier=self.supplier)
		second = self.bank_transaction(withdrawal=2, description=description, supplier=self.supplier)
		doc.append(
			"fee_debits",
			{"settlement_register_fee": doc.fees[0].name, "bank_transaction": first, "amount": 1},
		)
		fill_fee_debits(doc)
		debits = [row.bank_transaction for row in doc.fee_debits]
		self.assertEqual(debits, [first, second])

	def test_reconciled_fee_debit_copies_its_journal_entry(self):
		doc = self.register(
			"MAIB POS",
			"MAIB-reconciled-fee",
			[self.row(100, 3, 97, "RRN-FEE")],
		)
		bank_transaction = self.bank_transaction(
			withdrawal=3,
			description="Retinerea comisionului-operatiunile acceptare card",
		)
		doc.append(
			"fee_debits",
			{"settlement_register_fee": doc.fees[0].name, "bank_transaction": bank_transaction, "amount": 3},
		)
		doc.save()
		self.assertFalse(doc.fee_debits[0].journal_entry)
		journal = self.journal(3)
		bank = frappe.get_doc("Bank Transaction", bank_transaction)
		bank.append(
			"payment_entries",
			{"payment_document": "Journal Entry", "payment_entry": journal, "allocated_amount": 3},
		)
		bank.save()
		doc.save()
		doc.reload()
		self.assertEqual(doc.fee_debits[0].journal_entry, journal)
		self.assertFalse(doc.fees[0].journal_created)

	def test_maib_pos_search_does_not_guess_a_payment_without_a_reference(self):
		doc = self.register(
			"MAIB POS",
			"MAIB-no-reference",
			[self.row(100, 2.5, 97.5, "RRN-SEARCH")],
		)
		if _invoice_reference_field():
			invoice = self.pos_invoice(100, reference="RRN-SEARCH")
			fill_payment_documents(doc)
			self.assertEqual(doc.payments[0].sales_invoice, invoice)
			return
		self.pos_invoice(100)
		fill_payment_documents(doc)
		self.assertFalse(doc.payments[0].payment_entry)
		self.assertFalse(doc.payments[0].sales_invoice)

	def _inbox_with_register_file(self, folder, filename):
		if not frappe.db.exists("DocType", "Supplier Inbox Email"):
			self.skipTest("Supplier Inbox is not installed")
		if frappe.db.exists("DocType", "Supplier Inbox Settings"):
			frappe.db.set_single_value("Supplier Inbox Settings", "enabled", 1)
		settings = frappe.get_single("Settlements Settings")
		settings.sources = [
			row for row in settings.sources if row.source != "NovaPay" or row.company == COMPANY
		]
		settings.save()
		mail = frappe.get_doc({"doctype": "Supplier Inbox Email"}).insert(ignore_permissions=True)
		path = EXAMPLES / folder / filename
		attached = save_file(path.name, path.read_bytes(), "Supplier Inbox Email", mail.name, is_private=1)
		if attached.file_name != path.name:
			frappe.db.set_value("File", attached.name, "file_name", path.name, update_modified=False)
		frappe.db.delete(
			"Supplier Inbox Email Handler",
			{"parent": mail.name, "handler": "erpnext_moldova_settlements.inbox.handle_inbound_email"},
		)
		mail.reload()
		mail.append(
			"handlers",
			{
				"handler": "erpnext_moldova_settlements.inbox.handle_inbound_email",
				"status": "Queued",
			},
		)
		mail.save(ignore_permissions=True)
		return mail.name

	def _run_inbox_handler(self, mail):
		from erpnext_moldova_inbox.moldova_supplier_inbox.dispatch import run_handler

		run_handler(mail, "erpnext_moldova_settlements.inbox.handle_inbound_email")
		row = self._inbox_handler_row(mail)
		self.assertEqual(row.status, "Processed", row.error)
		return row.reference_name

	def _inbox_handler_row(self, mail):
		return frappe.db.get_value(
			"Supplier Inbox Email Handler",
			{"parent": mail, "handler": "erpnext_moldova_settlements.inbox.handle_inbound_email"},
			["status", "reference_doctype", "reference_name", "error"],
			as_dict=True,
		)

	def from_file(self, folder, filename):
		path = EXAMPLES / folder / filename
		attached = save_file(path.name, path.read_bytes(), None, None, is_private=1)
		if attached.file_name != path.name:
			frappe.db.set_value("File", attached.name, "file_name", path.name, update_modified=False)
		doc = frappe.new_doc("Settlement Register")
		doc.company = COMPANY
		doc.source_file = attached.file_url
		doc.insert()
		return frappe.get_doc(doc.doctype, doc.name)

	def register(self, source, number, rows):
		doc = frappe.new_doc("Settlement Register")
		doc.company = COMPANY
		doc.source = source
		doc.register_number = number
		doc.posting_date = rows[0]["transfer_date"]
		doc.currency = "MDL"
		doc.clearing_account = self.clearing
		doc.fee_account = self.fee
		doc.bank_account = self.bank_account
		doc.mode_of_payment = self.mode
		for row in rows:
			doc.append("payments", row)
		doc.insert()
		return doc

	def row(self, payment, fee, net, external_number, customer=None):
		values = {
			"transfer_date": "2026-09-07",
			"payment_amount": payment,
			"fee_amount": fee,
			"net_amount": net,
			"external_number": external_number,
		}
		if customer:
			values["customer"] = customer
		return values

	def payment(self, amount, paid_to=None):
		payment = frappe.new_doc("Payment Entry")
		payment.payment_type = "Receive"
		payment.company = COMPANY
		payment.posting_date = "2026-09-07"
		payment.mode_of_payment = self.mode
		payment.party_type = "Customer"
		payment.party = self.customer
		payment.paid_amount = amount
		payment.received_amount = amount
		payment.paid_to = paid_to or self.clearing
		payment.reference_no = frappe.generate_hash(length=10)
		payment.reference_date = payment.posting_date
		payment.setup_party_account_field()
		payment.set_missing_values()
		payment.paid_to = paid_to or self.clearing
		payment.paid_amount = amount
		payment.received_amount = amount
		payment.mode_of_payment = self.mode
		payment.insert()
		payment.submit()
		return payment.name

	def pos_invoice(self, amount, reference=None):
		invoice = frappe.new_doc("Sales Invoice")
		invoice.company = COMPANY
		invoice.customer = self.customer
		invoice.is_pos = 1
		invoice.currency = "MDL"
		invoice.set_posting_time = 1
		invoice.posting_date = "2026-09-07"
		invoice.append(
			"items",
			{
				"item_code": self.item,
				"qty": 1,
				"rate": amount,
				"income_account": self.income,
				"cost_center": frappe.get_cached_value("Company", COMPANY, "cost_center"),
			},
		)
		invoice.append(
			"payments",
			{"mode_of_payment": self.mode, "amount": amount, "account": self.clearing},
		)
		field = _invoice_reference_field()
		if reference and field:
			invoice.set(field, reference)
		invoice.insert()
		invoice.submit()
		return invoice.name

	def bank_transaction(self, withdrawal=0, deposit=0, description="", supplier=None):
		doc = frappe.new_doc("Bank Transaction")
		doc.date = "2026-09-07"
		doc.company = COMPANY
		doc.bank_account = self.bank_account
		doc.currency = "MDL"
		doc.withdrawal = withdrawal
		doc.deposit = deposit
		doc.description = description
		if supplier:
			doc.party_type = "Supplier"
			doc.party = supplier
		doc.insert()
		doc.submit()
		return doc.name

	def journal(self, amount):
		journal = frappe.new_doc("Journal Entry")
		journal.voucher_type = "Journal Entry"
		journal.company = COMPANY
		journal.posting_date = "2026-09-07"
		journal.append(
			"accounts",
			{
				"account": self.fee,
				"debit_in_account_currency": amount,
				"cost_center": frappe.get_cached_value("Company", COMPANY, "cost_center"),
			},
		)
		journal.append(
			"accounts",
			{"account": self.clearing, "credit_in_account_currency": amount},
		)
		journal.insert()
		journal.submit()
		return journal.name

	def _settings(self, create_payment_if_missing, search_payments):
		settings = frappe.get_single("Settlements Settings")
		settings.sources = [row for row in settings.sources if row.company != COMPANY]
		for row in settings.sources:
			if not row.supplier:
				row.supplier = self.supplier
			if not row.deposit_description:
				row.deposit_description = DEPOSIT_PATTERNS.get(row.source) or "Settlement"
		for source in ("NovaPay", "MegaMega", "MAIB POS", "MAIB Ecomm"):
			settings.append(
				"sources",
				{
					"company": COMPANY,
					"source": source,
					"clearing_account": self.clearing,
					"fee_account": self.fee,
					"bank_account": self.bank_account,
					"mode_of_payment": self.mode,
					"default_customer": self.customer,
					"supplier": self.supplier,
					"search_payments": search_payments,
					"create_payment_if_missing": create_payment_if_missing if source != "MAIB POS" else 0,
				},
			)
		settings.save()


def _ensure_currency():
	if frappe.db.exists("Currency", "MDL"):
		frappe.db.set_value("Currency", "MDL", "enabled", 1)
		return
	frappe.get_doc(
		{
			"doctype": "Currency",
			"currency_name": "MDL",
			"enabled": 1,
			"fraction": "Ban",
			"fraction_units": 100,
			"smallest_currency_fraction_value": 0.01,
			"symbol": "L",
		}
	).insert(ignore_permissions=True)


def _ensure_company():
	if frappe.db.exists("Company", COMPANY):
		return
	frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": COMPANY,
			"abbr": "STL",
			"default_currency": "MDL",
			"country": "Moldova, Republic of",
		}
	).insert(ignore_permissions=True)


def _ledger(company, root_type, account_name, account_type=None):
	existing = frappe.db.get_value("Account", {"company": company, "account_name": account_name}, "name")
	if existing:
		return existing
	parent = frappe.db.get_value(
		"Account",
		{"company": company, "root_type": root_type, "is_group": 1},
		"name",
		order_by="lft asc",
	)
	account = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": account_name,
			"parent_account": parent,
			"company": company,
			"root_type": root_type,
			"account_type": account_type,
			"is_group": 0,
		}
	)
	account.insert(ignore_permissions=True)
	return account.name


def _supplier(name):
	existing = frappe.db.get_value("Supplier", {"supplier_name": name}, "name")
	if existing:
		return existing
	supplier = frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": name,
			"supplier_group": "All Supplier Groups",
		}
	)
	supplier.insert(ignore_permissions=True)
	return supplier.name


def _customer(name):
	existing = frappe.db.get_value("Customer", {"customer_name": name}, "name")
	if existing:
		frappe.db.set_value("Customer", existing, "customer_type", "Individual", update_modified=False)
		return existing
	group = _leaf(
		"Customer Group",
		"_Settlements Customer Group",
		"All Customer Groups",
		"customer_group_name",
		"parent_customer_group",
	)
	territory = _leaf(
		"Territory",
		"_Settlements Territory",
		"All Territories",
		"territory_name",
		"parent_territory",
	)
	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Individual",
			"customer_group": group,
			"territory": territory,
		}
	)
	customer.insert(ignore_permissions=True)
	return customer.name


def _mode_of_payment(account):
	name = "_Settlements Card"
	if frappe.db.exists("Mode of Payment", name):
		mode = frappe.get_doc("Mode of Payment", name)
	else:
		mode = frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": name, "type": "Bank"})
	if not any(row.company == COMPANY for row in mode.accounts):
		mode.append("accounts", {"company": COMPANY, "default_account": account})
	mode.save(ignore_permissions=True)
	return mode.name


def _bank_account(account):
	bank = "_Settlements Bank"
	if not frappe.db.exists("Bank", bank):
		frappe.get_doc({"doctype": "Bank", "bank_name": bank}).insert(ignore_permissions=True)
	existing = frappe.db.get_value("Bank Account", {"account": account, "company": COMPANY}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Bank Account",
			"account_name": "_Settlements Clearing Bank",
			"bank": bank,
			"account": account,
			"company": COMPANY,
			"is_company_account": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _item():
	code = "_Settlements Item"
	if frappe.db.exists("Item", code):
		return code
	group = _leaf(
		"Item Group",
		"_Settlements Item Group",
		"All Item Groups",
		"item_group_name",
		"parent_item_group",
	)
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_group": group,
			"stock_uom": "Nos",
			"is_stock_item": 0,
		}
	).insert(ignore_permissions=True)
	return code


def _leaf(doctype, name, root_name, name_field, parent_field):
	existing = frappe.db.get_value(doctype, {"is_group": 0}, "name")
	if existing:
		return existing
	if not frappe.db.exists(doctype, root_name):
		root = frappe.get_doc({"doctype": doctype, name_field: root_name, "is_group": 1})
		root.insert(ignore_permissions=True)
	leaf = frappe.get_doc(
		{"doctype": doctype, name_field: name, parent_field: root_name, "is_group": 0}
	)
	leaf.insert(ignore_permissions=True)
	return leaf.name


def _fiscal_year():
	from erpnext.accounts.utils import get_fiscal_year

	try:
		get_fiscal_year("2026-09-07", company=COMPANY, verbose=0)
		return
	except Exception:
		pass
	if frappe.db.exists("Fiscal Year", "2026"):
		year = frappe.get_doc("Fiscal Year", "2026")
		if not any(row.company == COMPANY for row in year.companies):
			year.append("companies", {"company": COMPANY})
			year.save(ignore_permissions=True)
		return
	frappe.get_doc(
		{
			"doctype": "Fiscal Year",
			"year": "2026",
			"year_start_date": "2026-01-01",
			"year_end_date": "2026-12-31",
			"companies": [{"company": COMPANY}],
		}
	).insert(ignore_permissions=True)
