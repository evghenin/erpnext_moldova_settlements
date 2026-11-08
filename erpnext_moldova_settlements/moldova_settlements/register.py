# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

"""Load a supplier file into a register and post or match its documents."""

import frappe
from frappe import _
from frappe.model.naming import set_new_name
from frappe.utils import cint, flt, getdate

from erpnext_moldova_settlements.moldova_settlements.parsers.register_file import (
	CARD_FEE_DESCRIPTION,
	AmountMismatch,
	AutorizatReport,
	RegisterFileError,
	UnreadableDate,
	UnreadableTime,
	parse_register_file,
)

MONEY_FIELDS = (
	"payment_amount",
	"fee_amount",
	"net_amount",
	"cash_amount",
	"reversal_amount",
	"reversal_cash_amount",
	"reversed_fee",
	"instant_discount",
)
REFERENCE_FIELD = "referinta_tranzactiei"


def read_source_file(doc):
	if doc.payments or not doc.source_file:
		return
	path, filename = _attached_file(doc.source_file)
	try:
		parsed = parse_register_file(path, filename)
	except AutorizatReport:
		frappe.throw(_("The autorizat report does not create a register."))
	except AmountMismatch as exc:
		frappe.throw(
			_(
				"File amounts do not match on row {0}: payment {1}, fee {2}, net {3}."
			).format(exc.label, exc.payment, exc.fee, exc.net)
		)
	except UnreadableDate as exc:
		frappe.throw(_("Cannot read the date {0}.").format(exc.text))
	except UnreadableTime as exc:
		frappe.throw(_("Cannot read the transaction time {0}.").format(exc.text))
	except RegisterFileError as exc:
		frappe.throw(_(str(exc)))

	_reject_duplicate_register(parsed["register_number"])
	doc.source = parsed["source"]
	doc.register_number = parsed["register_number"]
	doc.posting_date = parsed["posting_date"]
	if parsed.get("currency"):
		doc.currency = parsed["currency"]
	if not doc.company:
		doc.company = _only_company(parsed["source"])
	for row in parsed["payments"]:
		values = {}
		for key, value in row.items():
			if value in (None, ""):
				continue
			values[key] = str(value) if key in MONEY_FIELDS else value
		doc.append("payments", values)
	copy_source_settings(doc)


def validate_register(doc):
	_keep_submitted_payment_rows(doc)
	if not doc.payments:
		frappe.throw(_("Attach the supplier file before saving."))
	if not doc.company:
		frappe.throw(_("Select a company for {0}.").format(doc.source))
	if not doc.currency:
		doc.currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	if not doc.currency:
		frappe.throw(_("Set the company."))
	copy_source_settings(doc)
	_validate_accounts(doc)
	_validate_payment_links(doc)
	_validate_external_numbers(doc)
	sync_groups(doc)
	_adopt_ecomm_links(doc)
	_validate_debits(doc)
	for table in ("payments", "fees", "fee_debits", "deposits"):
		for row in doc.get(table):
			row.currency = doc.currency
	_set_totals(doc)
	_apply_row_customers(doc)
	_copy_reconciled_vouchers(doc)
	_set_bullets(doc)
	if doc.docstatus == 1:
		doc.status = "Reconciled" if register_is_reconciled(doc) else "Unreconciled"
	_link_fee_payments(doc)
	sync_reference_rows(doc)


def _keep_submitted_payment_rows(doc):
	if doc.docstatus != 1:
		return
	previous = doc.get_doc_before_save()
	if not previous or previous.docstatus != 1:
		return
	before = {row.name for row in previous.payments}
	after = {row.name for row in doc.payments}
	if before != after:
		frappe.throw(_("Payment rows cannot be added or removed after the register is submitted."))


def refresh_submitted_register(doc):
	_copy_reconciled_vouchers(doc)
	_set_bullets(doc)
	doc.status = "Reconciled" if register_is_reconciled(doc) else "Unreconciled"
	_link_fee_payments(doc)
	sync_reference_rows(doc)


def before_submit_register(doc):
	if doc.source != "MAIB POS":
		_create_fee_entries(doc)
	_copy_reconciled_vouchers(doc)
	doc.status = "Reconciled" if register_is_reconciled(doc) else "Unreconciled"
	_set_bullets(doc)
	sync_reference_rows(doc)


def before_cancel_register(doc):
	doc.ignore_linked_doctypes = ("Journal Entry", "Payment Entry")
	_block_adopted_documents(doc)
	for row in doc.payments:
		if row.payment_created and row.payment_entry:
			_cancel_linked("Payment Entry", row.payment_entry)
		row.payment_entry = None
		row.sales_invoice = None
		row.payment_created = 0
	for row in doc.fees:
		if row.journal_created and row.journal_entry:
			_cancel_linked("Journal Entry", row.journal_entry)
		row.journal_entry = None
		row.journal_created = 0
	for row in doc.fee_debits:
		row.journal_entry = None
	for row in doc.deposits:
		row.payment_entry = None
		row.journal_entry = None
	sync_reference_rows(doc)


def refresh_registers_for_bank_transaction(bt, method=None):
	parents = set()
	for child in ("Settlement Register Fee Debit", "Settlement Register Deposit"):
		parents.update(frappe.get_all(child, filters={"bank_transaction": bt.name}, pluck="parent"))
	for name in parents:
		if frappe.db.get_value("Settlement Register", name, "docstatus") != 1:
			continue
		doc = frappe.get_doc("Settlement Register", name)
		for row in doc.deposits:
			if row.bank_transaction != bt.name:
				continue
			previous = (row.payment_entry, row.journal_entry)
			_copy_deposit_voucher(row)
			if (row.payment_entry, row.journal_entry) != previous:
				row.db_update()
		for row in doc.fee_debits:
			if row.bank_transaction != bt.name or row.journal_entry:
				continue
			journal_entry = _single_reconciled_journal_entry(bt.name)
			if not journal_entry:
				continue
			row.journal_entry = journal_entry
			row.db_update()
		_set_bullets(doc)
		for row in (*doc.payments, *doc.fees, *doc.deposits):
			frappe.db.set_value(row.doctype, row.name, "row_bullet", row.row_bullet, update_modified=False)
		sync_reference_rows(doc)
		_replace_reference_rows(doc)
		status = "Reconciled" if register_is_reconciled(doc) else "Unreconciled"
		if doc.status != status:
			frappe.db.set_value("Settlement Register", name, "status", status, update_modified=False)


def _replace_reference_rows(doc):
	frappe.db.delete("Settlement Register Reference", {"parent": doc.name})
	for index, row in enumerate(doc.reference_rows, start=1):
		row.parent = doc.name
		row.parenttype = "Settlement Register"
		row.parentfield = "reference_rows"
		row.docstatus = doc.docstatus
		row.idx = index
		if not row.name:
			set_new_name(row)
		row.db_insert()


def fill_payment_documents(doc):
	settings = get_source_settings(doc.company, doc.source)
	if not settings or not cint(settings.search_payments):
		frappe.throw(_("Searching for payments is turned off for this source."))
	used_payments, used_invoices = _linked_documents(doc)
	reference_field = _invoice_reference_field() if doc.source == "MAIB POS" else None
	for row in doc.payments:
		if row.payment_entry or row.sales_invoice:
			continue
		if doc.source == "MAIB POS" and not reference_field:
			continue
		candidates = _free_candidates(doc, row, reference_field, used_payments, used_invoices)
		if len(candidates) != 1:
			continue
		field, name = candidates[0]
		row.set(field, name)
		if not row.customer:
			party = _document_customer(field, name)
			if party:
				row.customer = party
		(used_payments if field == "payment_entry" else used_invoices).add(name)
	_set_bullets(doc)


def fill_fee_debits(doc):
	if doc.source != "MAIB POS":
		return
	settings = _payout_settings(doc)
	used = _linked_bank_transactions(doc)
	for fee in doc.fees:
		existing = [
			row
			for row in doc.fee_debits
			if row.settlement_register_fee == fee.name and row.bank_transaction
		]
		existing_sum = sum(flt(row.amount) for row in existing)
		if existing and flt(existing_sum, 2) == flt(fee.fee_amount, 2):
			continue
		fresh = [
			bt
			for bt in _bank_transactions(
				doc, fee.credit_date, CARD_FEE_DESCRIPTION, "withdrawal", settings.supplier
			)
			if bt.name not in used
		]
		incoming = sum(flt(bt.withdrawal) for bt in fresh)
		if flt(existing_sum + incoming, 2) != flt(fee.fee_amount, 2):
			continue
		for bt in fresh:
			doc.append(
				"fee_debits",
				{
					"settlement_register_fee": fee.name,
					"bank_transaction": bt.name,
					"amount": flt(bt.withdrawal, 2),
				},
			)
			used.add(bt.name)
	_set_bullets(doc)


def fill_deposit_transactions(doc):
	settings = _payout_settings(doc)
	description = settings.deposit_description
	used = _linked_bank_transactions(doc)
	for row in doc.deposits:
		if row.bank_transaction:
			continue
		matches = [
			bt
			for bt in _bank_transactions(doc, row.credit_date, description, "deposit", settings.supplier)
			if bt.name not in used and flt(bt.deposit, 2) == flt(row.transfer_amount, 2)
		]
		if "ecomm" not in _normalize(description):
			matches = [bt for bt in matches if "ecomm" not in _normalize(bt.description)]
		if len(matches) != 1:
			continue
		row.bank_transaction = matches[0].name
		used.add(matches[0].name)
		_copy_deposit_voucher(row)
	_set_bullets(doc)


def register_is_reconciled(doc):
	if not doc.payments or not doc.deposits:
		return False
	for row in doc.payments:
		if not row.payment_entry and not row.sales_invoice:
			return False
	for row in doc.deposits:
		if _bank_status(row.bank_transaction) != "Reconciled":
			return False
	if doc.source == "MAIB POS":
		return all(_debits_ready(doc, fee) for fee in doc.fees)
	return all(row.journal_entry or not flt(row.fee_amount) for row in doc.fees)


def sync_groups(doc):
	dates = []
	for row in doc.payments:
		if not row.transfer_date:
			frappe.throw(_("A payment row has no date."))
		credit_date = str(getdate(row.transfer_date))
		if credit_date not in dates:
			dates.append(credit_date)
	fees = _collapse_dated_rows(doc, "fees", "credit_date")
	deposits = _collapse_dated_rows(doc, "deposits", "credit_date")
	for credit_date in dates:
		amount = _sum_rows(doc.payments, credit_date, "fee_amount")
		transfer_field = "payment_amount" if doc.source == "MAIB POS" else "net_amount"
		transfer = _sum_rows(doc.payments, credit_date, transfer_field)
		fee = fees.get(credit_date)
		if not fee:
			fee = doc.append("fees", {"credit_date": credit_date})
			set_new_name(fee)
			fees[credit_date] = fee
		fee.fee_amount = amount
		if doc.source == "MAIB POS":
			fee.journal_entry = None
			fee.journal_created = 0
		deposit = deposits.get(credit_date)
		if not deposit:
			deposit = doc.append("deposits", {"credit_date": credit_date})
			set_new_name(deposit)
			deposits[credit_date] = deposit
		deposit.transfer_amount = transfer
		for row in doc.payments:
			if str(getdate(row.transfer_date)) != credit_date:
				continue
			row.settlement_register_fee = fee.name
			row.settlement_register_deposit = deposit.name
	for credit_date, row in list(fees.items()):
		if credit_date in dates:
			continue
		if any(debit.settlement_register_fee == row.name for debit in doc.fee_debits):
			frappe.throw(_("Fee {0} still has debits.").format(credit_date))
		doc.remove(row)
	for credit_date, row in list(deposits.items()):
		if credit_date in dates:
			continue
		if row.bank_transaction:
			frappe.throw(_("Deposit {0} still has a Bank Transaction.").format(credit_date))
		doc.remove(row)


def sync_reference_rows(doc):
	wanted = []
	seen = set()

	def add(field, value):
		if not value or (field, value) in seen:
			return
		seen.add((field, value))
		wanted.append((field, value))

	for row in doc.fees:
		add("journal_entry", row.journal_entry)
	for row in doc.fee_debits:
		add("journal_entry", row.journal_entry)
		add("bank_transaction", row.bank_transaction)
	for row in doc.deposits:
		add("journal_entry", row.journal_entry)
		add("payment_entry", row.payment_entry)
		add("bank_transaction", row.bank_transaction)
	for row in doc.payments:
		add("payment_entry", row.payment_entry)
		add("sales_invoice", row.sales_invoice)
	current = [_filled_reference(row) for row in doc.reference_rows]
	current = [item for item in current if item]
	if current == wanted:
		return
	for row in list(doc.reference_rows):
		doc.remove(row)
	for field, value in wanted:
		added = doc.append("reference_rows", {field: value})
		set_new_name(added)


def copy_source_settings(doc):
	row = get_source_settings(doc.company, doc.source)
	if not row:
		return
	for field in ("clearing_account", "fee_account", "bank_account", "mode_of_payment"):
		if not doc.get(field) and row.get(field):
			doc.set(field, row.get(field))


def get_source_settings(company, source):
	if not company or not source or not frappe.db.exists("DocType", "Settlements Source"):
		return None
	rows = frappe.get_all(
		"Settlements Source",
		filters={"parent": "Settlements Settings", "company": company, "source": source},
		fields=[
			"clearing_account",
			"fee_account",
			"bank_account",
			"mode_of_payment",
			"search_payments",
			"create_payment_if_missing",
			"default_customer",
			"supplier",
			"deposit_description",
		],
		limit=1,
	)
	return rows[0] if rows else None


def _attached_file(file_url):
	row = frappe.db.get_value("File", {"file_url": file_url}, ["name", "file_name"], as_dict=True)
	if not row:
		frappe.throw(_("Attach the supplier file before saving."))
	return frappe.get_doc("File", row.name).get_full_path(), row.file_name


def _only_company(source):
	if not frappe.db.exists("DocType", "Settlements Source"):
		frappe.throw(_("Set Settlements Settings for {0}.").format(source))
	companies = frappe.get_all(
		"Settlements Source",
		filters={"parent": "Settlements Settings", "source": source},
		pluck="company",
	)
	if len(companies) == 1:
		return companies[0]
	if not companies:
		frappe.throw(_("Set Settlements Settings for {0}.").format(source))
	frappe.throw(_("Select a company for {0}.").format(source))


def active_register_name(register_number):
	"""Return the draft or submitted register with this supplier number."""
	if not register_number:
		return None
	return frappe.db.get_value(
		"Settlement Register",
		{"register_number": register_number, "docstatus": ["<", 2]},
		"name",
	)


def _reject_duplicate_register(register_number):
	if active_register_name(register_number):
		frappe.throw(_("Register {0} already exists.").format(register_number))


def _validate_accounts(doc):
	for field in ("clearing_account", "fee_account"):
		account = doc.get(field)
		if account and frappe.db.get_value("Account", account, "company") != doc.company:
			frappe.throw(_("The account {0} belongs to another company.").format(account))
	if doc.bank_account and frappe.db.get_value("Bank Account", doc.bank_account, "company") != doc.company:
		frappe.throw(_("The bank account belongs to another company."))


def _validate_payment_links(doc):
	for row in doc.payments:
		if row.payment_entry and row.sales_invoice:
			frappe.throw(_("Payment row needs one link: Payment Entry or Sales Invoice."))
		if not row.payment_entry and not row.sales_invoice:
			continue
		if not doc.clearing_account:
			frappe.throw(_("Set the clearing account."))
		if row.payment_entry:
			_validate_linked_payment(doc, row)
		else:
			_validate_linked_invoice(doc, row)


def _validate_linked_payment(doc, row):
	payment = frappe.db.get_value(
		"Payment Entry",
		row.payment_entry,
		[
			"docstatus",
			"company",
			"payment_type",
			"party_type",
			"party",
			"paid_amount",
			"paid_to",
			"paid_to_account_currency",
		],
		as_dict=True,
	)
	if (
		not payment
		or payment.docstatus != 1
		or payment.company != doc.company
		or payment.payment_type != "Receive"
		or payment.party_type != "Customer"
	):
		frappe.throw(_("Payment Entry {0} cannot be linked to this register.").format(row.payment_entry))
	if row.customer and row.customer != payment.party:
		frappe.throw(_("Payment Entry {0} belongs to another customer.").format(row.payment_entry))
	if flt(payment.paid_amount, 2) != flt(row.payment_amount, 2):
		frappe.throw(_("Payment Entry {0} amount does not match the payment row.").format(row.payment_entry))
	if payment.paid_to != doc.clearing_account:
		frappe.throw(_("Payment Entry {0} is not paid to the clearing account.").format(row.payment_entry))
	if payment.paid_to_account_currency != doc.currency:
		frappe.throw(_("Payment Entry {0} is in another currency.").format(row.payment_entry))


def _validate_linked_invoice(doc, row):
	invoice = frappe.db.get_value(
		"Sales Invoice",
		row.sales_invoice,
		["docstatus", "company", "customer", "is_pos", "currency"],
		as_dict=True,
	)
	if not invoice or invoice.docstatus != 1 or invoice.company != doc.company or not invoice.is_pos:
		frappe.throw(_("Sales Invoice {0} cannot be linked to this register.").format(row.sales_invoice))
	if row.customer and row.customer != invoice.customer:
		frappe.throw(_("Sales Invoice {0} belongs to another customer.").format(row.sales_invoice))
	if invoice.currency != doc.currency:
		frappe.throw(_("Sales Invoice {0} is in another currency.").format(row.sales_invoice))
	if not _invoice_has_payment(row.sales_invoice, row.payment_amount):
		frappe.throw(_("Sales Invoice {0} amount does not match the payment row.").format(row.sales_invoice))
	if not _invoice_has_payment(row.sales_invoice, row.payment_amount, account=doc.clearing_account):
		frappe.throw(_("Sales Invoice {0} is not paid to the clearing account.").format(row.sales_invoice))


def _validate_external_numbers(doc):
	seen = set()
	for row in doc.payments:
		if not row.external_number:
			continue
		if row.external_number in seen:
			frappe.throw(_("Payment {0} is already in this register.").format(row.external_number))
		seen.add(row.external_number)
		others = frappe.db.sql(
			"""
			select r.name, p.payment_amount, p.fee_amount, p.net_amount, p.transfer_date
			from `tabSettlement Register Payment` p
			inner join `tabSettlement Register` r on r.name = p.parent
			where p.external_number = %s and r.source = %s and r.docstatus < 2 and r.name != %s
			""",
			(row.external_number, doc.source, doc.name or ""),
			as_dict=True,
		)
		for other in others:
			if doc.source == "MAIB Ecomm" and _same_payment(row, other):
				continue
			frappe.throw(
				_("Payment {0} is already in register {1}.").format(row.external_number, other.name)
			)


def _adopt_ecomm_links(doc):
	if doc.source != "MAIB Ecomm":
		return
	payments, fees, deposits = _ecomm_siblings(doc)
	_adopt_payment_links(doc, payments)
	_adopt_day_links(doc, payments, fees, deposits)
	doc.coverage_gaps = _coverage_gaps(doc, payments)


def _ecomm_siblings(doc):
	if not doc.company:
		return [], [], []
	parent = doc.name or ""
	payments = frappe.db.sql(
		"""
		select r.name as register, p.external_number, p.transfer_date,
			p.payment_amount, p.fee_amount, p.net_amount,
			p.payment_entry, p.sales_invoice, p.customer, p.payment_created
		from `tabSettlement Register Payment` p
		inner join `tabSettlement Register` r on r.name = p.parent
		where r.source = 'MAIB Ecomm' and r.company = %s and r.docstatus < 2 and r.name != %s
		""",
		(doc.company, parent),
		as_dict=True,
	)
	fees = frappe.db.sql(
		"""
		select r.name as register, c.credit_date, c.fee_amount, c.journal_entry, c.journal_created
		from `tabSettlement Register Fee` c
		inner join `tabSettlement Register` r on r.name = c.parent
		where r.source = 'MAIB Ecomm' and r.company = %s and r.docstatus < 2 and r.name != %s
		""",
		(doc.company, parent),
		as_dict=True,
	)
	deposits = frappe.db.sql(
		"""
		select r.name as register, d.credit_date, d.transfer_amount, d.bank_transaction,
			d.payment_entry, d.journal_entry
		from `tabSettlement Register Deposit` d
		inner join `tabSettlement Register` r on r.name = d.parent
		where r.source = 'MAIB Ecomm' and r.company = %s and r.docstatus < 2 and r.name != %s
		""",
		(doc.company, parent),
		as_dict=True,
	)
	return payments, fees, deposits


def _adopt_payment_links(doc, payments):
	by_number = {}
	for other in payments:
		by_number.setdefault(other.external_number, []).append(other)
	for row in doc.payments:
		donors = [
			other
			for other in by_number.get(row.external_number, [])
			if _same_payment(row, other)
		]
		donors.sort(key=lambda other: (cint(other.payment_created), bool(other.payment_entry or other.sales_invoice)), reverse=True)
		for other in donors:
			if row.payment_entry or row.sales_invoice:
				break
			if other.payment_entry:
				row.payment_entry = other.payment_entry
				party = _document_customer("payment_entry", other.payment_entry)
				if party:
					row.customer = party
				break
			if other.sales_invoice:
				row.sales_invoice = other.sales_invoice
				party = _document_customer("sales_invoice", other.sales_invoice)
				if party:
					row.customer = party
				break
			if not row.customer and other.customer:
				row.customer = other.customer


def _adopt_day_links(doc, payments, fees, deposits):
	grouped = {}
	for other in payments:
		grouped.setdefault((other.register, _credit_date(other.transfer_date)), []).append(other)
	for credit_date, rows in _payments_by_date(doc).items():
		registers = _matching_days(rows, grouped)
		if not registers:
			continue
		register = _best_day_register(registers, credit_date, fees, deposits)
		fee = _row_for_date(doc.fees, credit_date)
		donor = _preferred_day_row(
			[row for row in fees if row.register == register and _credit_date(row.credit_date) == credit_date],
			"journal_created",
			"journal_entry",
		)
		if fee and donor and not fee.journal_entry and donor.journal_entry:
			if flt(donor.fee_amount, 2) == flt(fee.fee_amount, 2):
				fee.journal_entry = donor.journal_entry
		deposit = _row_for_date(doc.deposits, credit_date)
		donor = _preferred_day_row(
			[row for row in deposits if row.register == register and _credit_date(row.credit_date) == credit_date],
			None,
			"bank_transaction",
		)
		if not deposit or not donor or flt(donor.transfer_amount, 2) != flt(deposit.transfer_amount, 2):
			continue
		if not deposit.bank_transaction and donor.bank_transaction:
			deposit.bank_transaction = donor.bank_transaction
		if not deposit.payment_entry and donor.payment_entry:
			deposit.payment_entry = donor.payment_entry
		if not deposit.journal_entry and donor.journal_entry:
			deposit.journal_entry = donor.journal_entry


def _matching_days(rows, grouped):
	numbers = _number_set(rows)
	fee = flt(sum(flt(row.fee_amount) for row in rows), 2)
	net = flt(sum(flt(row.net_amount) for row in rows), 2)
	found = []
	for (register, _credit), others in grouped.items():
		if _number_set(others) != numbers:
			continue
		if flt(sum(flt(row.fee_amount) for row in others), 2) != fee:
			continue
		if flt(sum(flt(row.net_amount) for row in others), 2) != net:
			continue
		found.append(register)
	return found


def _best_day_register(registers, credit_date, fees, deposits):
	def rank(register):
		journal = any(
			row.register == register
			and _credit_date(row.credit_date) == credit_date
			and cint(row.journal_created)
			and row.journal_entry
			for row in fees
		)
		bank = any(
			row.register == register and _credit_date(row.credit_date) == credit_date and row.bank_transaction
			for row in deposits
		)
		return (journal, bank)

	return max(registers, key=rank)


def _coverage_gaps(doc, payments):
	if not doc.payments:
		return ""
	dates = [_credit_date(row.transfer_date) for row in doc.payments]
	start, end = min(dates), max(dates)
	own = {row.external_number for row in doc.payments if row.external_number}
	others = {}
	for row in payments:
		if not row.external_number:
			continue
		credit_date = _credit_date(row.transfer_date)
		if credit_date < start or credit_date > end:
			continue
		others.setdefault(row.external_number, set()).add(row.register)
	lines = []
	for number in sorted(set(others) - own):
		registers = ", ".join(sorted(others[number]))
		lines.append(_("{0} is in {1} and not in this register.").format(number, registers))
	for number in sorted(own - set(others)):
		lines.append(_("{0} is not in another MAIB Ecomm register.").format(number))
	return "\n".join(lines)


def _block_adopted_documents(doc):
	if doc.source != "MAIB Ecomm" or not doc.name:
		return
	_block_created_links(
		doc.name,
		[row.payment_entry for row in doc.payments if row.payment_created and row.payment_entry],
		"Settlement Register Payment",
		"payment_entry",
		"payment_created",
		_("Register {0} uses Payment Entry {1} from this register. Cancel {0} first."),
	)
	_block_created_links(
		doc.name,
		[row.journal_entry for row in doc.fees if row.journal_created and row.journal_entry],
		"Settlement Register Fee",
		"journal_entry",
		"journal_created",
		_("Register {0} uses Journal Entry {1} from this register. Cancel {0} first."),
	)


def _block_created_links(register, names, child_doctype, field, created_field, message):
	if not names:
		return
	rows = frappe.db.sql(
		f"""
		select r.name as register, child.`{field}` as document
		from `tab{child_doctype}` child
		inner join `tabSettlement Register` r on r.name = child.parent
		where child.`{field}` in %s and ifnull(child.`{created_field}`, 0) = 0
			and r.docstatus < 2 and r.name != %s
		limit 1
		""",
		(tuple(names), register),
		as_dict=True,
	)
	if rows:
		frappe.throw(message.format(rows[0].register, rows[0].document))


def _partial_ecomm_days(doc):
	if doc.source != "MAIB Ecomm":
		return set()
	payments, _fees, _deposits = _ecomm_siblings(doc)
	grouped = {}
	for other in payments:
		grouped.setdefault((other.register, _credit_date(other.transfer_date)), []).append(other)
	blocked = set()
	for credit_date, rows in _payments_by_date(doc).items():
		if credit_date not in {key[1] for key in grouped}:
			continue
		if not _matching_days(rows, grouped):
			blocked.add(credit_date)
	return blocked


def _same_payment(row, other):
	return (
		flt(row.payment_amount, 2) == flt(other.payment_amount, 2)
		and flt(row.fee_amount, 2) == flt(other.fee_amount, 2)
		and flt(row.net_amount, 2) == flt(other.net_amount, 2)
		and _credit_date(row.transfer_date) == _credit_date(other.transfer_date)
	)


def _payments_by_date(doc):
	grouped = {}
	for row in doc.payments:
		grouped.setdefault(_credit_date(row.transfer_date), []).append(row)
	return grouped


def _credit_date(value):
	return str(getdate(value))


def _number_set(rows):
	return tuple(sorted(row.external_number or "" for row in rows))


def _row_for_date(rows, credit_date):
	for row in rows:
		if _credit_date(row.credit_date) == credit_date:
			return row
	return None


def _preferred_day_row(rows, created_field, link_field):
	if not rows:
		return None

	def rank(row):
		created = cint(getattr(row, created_field, 0)) if created_field else 0
		return (created, bool(getattr(row, link_field, None)))

	return max(rows, key=rank)


def _validate_debits(doc):
	for row in list(doc.fee_debits):
		if not row.bank_transaction and not row.settlement_register_fee:
			doc.remove(row)
	if doc.source != "MAIB POS":
		if doc.fee_debits:
			frappe.throw(_("Fee debits are only used for MAIB POS."))
		return
	names = {row.name for row in doc.fees}
	seen = set()
	for row in list(doc.fee_debits):
		if not row.bank_transaction and not row.settlement_register_fee:
			doc.remove(row)
			continue
		if len(doc.fees) == 1 and not row.settlement_register_fee:
			row.settlement_register_fee = doc.fees[0].name
		if row.settlement_register_fee not in names:
			frappe.throw(_("A fee debit is not linked to a fee row."))
		if not row.bank_transaction:
			continue
		if row.bank_transaction in seen:
			frappe.throw(_("Bank Transaction {0} is already on this register.").format(row.bank_transaction))
		seen.add(row.bank_transaction)
		owner = _bank_transaction_owner(row.bank_transaction, doc.name)
		if owner:
			frappe.throw(_("Bank Transaction {0} is already on register {1}.").format(row.bank_transaction, owner))
		row.amount = flt(
			frappe.db.get_value("Bank Transaction", row.bank_transaction, "withdrawal"), 2
		)


def _copy_reconciled_vouchers(doc):
	_copy_fee_journal_entries(doc)
	for row in doc.deposits:
		_copy_deposit_voucher(row)


def _copy_fee_journal_entries(doc):
	if doc.source != "MAIB POS":
		return
	for fee in doc.fees:
		for row in _debits_for(doc, fee):
			row.journal_entry = (
				_single_reconciled_journal_entry(row.bank_transaction) if row.bank_transaction else None
			)


def _create_fee_entries(doc):
	from erpnext_moldova_settlements.moldova_settlements.journal_entry import ensure_settlement_register_field

	ensure_settlement_register_field()
	cost_center = frappe.get_cached_value("Company", doc.company, "cost_center")
	partial_days = _partial_ecomm_days(doc)
	for row in doc.fees:
		if row.journal_entry or not flt(row.fee_amount):
			continue
		if _credit_date(row.credit_date) in partial_days:
			frappe.msgprint(
				_("Fee for {0} is not posted because that day differs from another MAIB Ecomm register.").format(
					_credit_date(row.credit_date)
				)
			)
			continue
		if not doc.fee_account or not doc.clearing_account:
			frappe.throw(_("Set the clearing account and the fee account."))
		journal_entry = frappe.new_doc("Journal Entry")
		journal_entry.voucher_type = "Journal Entry"
		journal_entry.company = doc.company
		journal_entry.posting_date = row.credit_date
		journal_entry.settlement_register = doc.name
		journal_entry.append(
			"accounts",
			{
				"account": doc.fee_account,
				"debit_in_account_currency": row.fee_amount,
				"cost_center": cost_center,
			},
		)
		journal_entry.append(
			"accounts",
			{
				"account": doc.clearing_account,
				"credit_in_account_currency": row.fee_amount,
			},
		)
		journal_entry.insert()
		journal_entry.submit()
		row.journal_entry = journal_entry.name
		row.journal_created = 1


def _payments_for_fee(doc, fee):
	linked = [row for row in doc.payments if row.settlement_register_fee == fee.name]
	if linked:
		return linked
	credit_date = _credit_date(fee.credit_date)
	return [row for row in doc.payments if row.transfer_date and _credit_date(row.transfer_date) == credit_date]


def _link_fee_payments(doc):
	for fee in doc.fees:
		rows = _payments_for_fee(doc, fee)
		numbers = []
		entries = []
		for row in rows:
			if row.external_number and row.external_number not in numbers:
				numbers.append(row.external_number)
			if row.payment_entry and row.payment_entry not in entries:
				entries.append(row.payment_entry)
		fee.external_number = ", ".join(numbers)
		fee.payment_entry = entries[0] if len(entries) == 1 else None


def _write_fee_journal(doc, fee):
	if not fee.journal_created or not fee.journal_entry:
		return
	if not frappe.db.exists("Journal Entry", fee.journal_entry):
		return
	frappe.db.set_value(
		"Journal Entry",
		fee.journal_entry,
		"settlement_register",
		doc.name,
		update_modified=False,
	)


def backfill_fee_links():
	from erpnext_moldova_settlements.moldova_settlements.journal_entry import ensure_settlement_register_field

	ensure_settlement_register_field()
	if not frappe.db.has_column("Settlement Register Fee", "external_number"):
		return
	for name in set(frappe.get_all("Settlement Register Fee", pluck="parent")):
		if frappe.db.get_value("Settlement Register", name, "docstatus") == 2:
			continue
		doc = frappe.get_doc("Settlement Register", name)
		_link_fee_payments(doc)
		for fee in doc.fees:
			frappe.db.set_value(
				"Settlement Register Fee",
				fee.name,
				{"external_number": fee.external_number, "payment_entry": fee.payment_entry},
				update_modified=False,
			)
			_write_fee_journal(doc, fee)


def create_payment_entries(doc):
	if doc.docstatus != 1:
		frappe.throw(_("Payments are created after the register is submitted."))
	settings = get_source_settings(doc.company, doc.source)
	if not settings or not cint(settings.create_payment_if_missing):
		frappe.throw(_("Creating payments is turned off for this source."))
	_create_missing_payments(doc)


def _create_missing_payments(doc):
	settings = get_source_settings(doc.company, doc.source)
	if not settings or not cint(settings.create_payment_if_missing):
		return
	for row in doc.payments:
		if row.payment_entry or row.sales_invoice or _is_reversal(row):
			continue
		if not row.customer or not doc.clearing_account or not flt(row.payment_amount):
			continue
		payment = frappe.new_doc("Payment Entry")
		payment.payment_type = "Receive"
		payment.company = doc.company
		payment.posting_date = row.transfer_date or doc.posting_date
		payment.party_type = "Customer"
		payment.party = row.customer
		payment.paid_amount = row.payment_amount
		payment.received_amount = row.payment_amount
		payment.mode_of_payment = doc.mode_of_payment
		payment.reference_no = row.external_number or doc.name
		payment.reference_date = payment.posting_date
		payment.paid_to = doc.clearing_account
		payment.remarks = doc.name
		payment.setup_party_account_field()
		payment.set_missing_values()
		payment.mode_of_payment = doc.mode_of_payment
		payment.paid_to = doc.clearing_account
		payment.paid_amount = row.payment_amount
		payment.received_amount = row.payment_amount
		payment.insert()
		payment.submit()
		row.payment_entry = payment.name
		row.payment_created = 1


def _apply_row_customers(doc):
	settings = get_source_settings(doc.company, doc.source)
	default_customer = settings.default_customer if settings else None
	for row in doc.payments:
		if row.payment_entry or row.sales_invoice:
			if not row.customer:
				party = _document_customer(
					"payment_entry" if row.payment_entry else "sales_invoice",
					row.payment_entry or row.sales_invoice,
				)
				if party:
					row.customer = party
			continue
		if not row.customer and default_customer and not _is_reversal(row):
			row.customer = default_customer


def _document_customer(field, name):
	if field == "payment_entry":
		party_type, party = frappe.db.get_value("Payment Entry", name, ["party_type", "party"]) or (None, None)
		return party if party_type == "Customer" else None
	return frappe.db.get_value("Sales Invoice", name, "customer")


def _free_candidates(doc, row, reference_field, used_payments, used_invoices, ignore_customer=False):
	return [
		item
		for item in _payment_candidates(doc, row, reference_field, ignore_customer)
		if item[1] not in (used_payments if item[0] == "payment_entry" else used_invoices)
	]


def _payment_candidates(doc, row, reference_field, ignore_customer=False):
	found = []
	payment_filters = {
		"company": doc.company,
		"docstatus": 1,
		"payment_type": "Receive",
		"paid_amount": flt(row.payment_amount, 2),
	}
	if doc.clearing_account:
		payment_filters["paid_to"] = doc.clearing_account
	if doc.mode_of_payment:
		payment_filters["mode_of_payment"] = doc.mode_of_payment
	if row.customer and not ignore_customer:
		payment_filters["party"] = row.customer
	if doc.source != "MAIB POS":
		found.extend(("payment_entry", name) for name in frappe.get_all("Payment Entry", filters=payment_filters, pluck="name"))
	invoice_filters = {"company": doc.company, "docstatus": 1, "is_pos": 1}
	if row.customer and not ignore_customer:
		invoice_filters["customer"] = row.customer
	if reference_field:
		invoice_filters[reference_field] = row.external_number
	elif doc.source == "MAIB POS":
		return []
	for name in frappe.get_all("Sales Invoice", filters=invoice_filters, pluck="name"):
		if _invoice_has_payment(name, row.payment_amount, doc.mode_of_payment if doc.source == "MAIB POS" else None):
			found.append(("sales_invoice", name))
	return found


def _invoice_has_payment(invoice, amount, mode_of_payment=None, account=None):
	filters = {"parent": invoice, "amount": flt(amount, 2)}
	if mode_of_payment:
		filters["mode_of_payment"] = mode_of_payment
	if account:
		filters["account"] = account
	return bool(frappe.db.exists("Sales Invoice Payment", filters))


def _invoice_reference_field():
	meta = frappe.get_meta("Sales Invoice")
	for fieldname in (REFERENCE_FIELD, f"custom_{REFERENCE_FIELD}"):
		if meta.has_field(fieldname):
			return fieldname
	return None


def _linked_documents(doc):
	payments, invoices = set(), set()
	for row in doc.payments:
		if row.payment_entry:
			payments.add(row.payment_entry)
		if row.sales_invoice:
			invoices.add(row.sales_invoice)
	if not doc.name:
		return payments, invoices
	rows = frappe.db.sql(
		"""
		select p.payment_entry, p.sales_invoice
		from `tabSettlement Register Payment` p
		inner join `tabSettlement Register` r on r.name = p.parent
		where r.docstatus < 2 and r.name != %s
		""",
		doc.name,
		as_dict=True,
	)
	for row in rows:
		if row.payment_entry:
			payments.add(row.payment_entry)
		if row.sales_invoice:
			invoices.add(row.sales_invoice)
	return payments, invoices


def _payout_settings(doc):
	settings = get_source_settings(doc.company, doc.source)
	if not settings or not settings.supplier or not settings.deposit_description:
		frappe.throw(_("Set the supplier and the deposit description."))
	if not doc.bank_account:
		frappe.throw(_("Set the bank account."))
	return settings


def _bank_transactions(doc, credit_date, description, amount_field, supplier):
	rows = frappe.get_all(
		"Bank Transaction",
		filters={
			"company": doc.company,
			"bank_account": doc.bank_account,
			"date": getdate(credit_date),
			"docstatus": 1,
			"status": ["!=", "Cancelled"],
		},
		fields=["name", "description", "withdrawal", "deposit", "party_type", "party"],
	)
	pattern = _normalize(description)
	return [
		row
		for row in rows
		if flt(row.get(amount_field)) > 0
		and pattern in _normalize(row.description)
		and row.party_type == "Supplier"
		and row.party == supplier
	]


def _linked_bank_transactions(doc):
	used = {row.bank_transaction for row in doc.fee_debits if row.bank_transaction}
	used.update(row.bank_transaction for row in doc.deposits if row.bank_transaction)
	if not doc.name:
		return used
	for child in ("Settlement Register Fee Debit", "Settlement Register Deposit"):
		for row in frappe.get_all(
			child,
			filters={"bank_transaction": ["is", "set"]},
			fields=["parent", "bank_transaction"],
		):
			if row.parent == doc.name:
				continue
			if frappe.db.get_value("Settlement Register", row.parent, "docstatus") != 2:
				used.add(row.bank_transaction)
	return used


def _bank_transaction_owner(bank_transaction, current):
	for child in ("Settlement Register Fee Debit", "Settlement Register Deposit"):
		for parent in frappe.get_all(child, filters={"bank_transaction": bank_transaction}, pluck="parent"):
			if parent == current:
				continue
			if frappe.db.get_value("Settlement Register", parent, "docstatus") != 2:
				return parent
	return None


def _is_submitted(doctype, name):
	return bool(name) and frappe.db.get_value(doctype, name, "docstatus") == 1


def _copy_deposit_voucher(row):
	if not row.bank_transaction:
		row.payment_entry = None
		row.journal_entry = None
		return
	if row.payment_entry or row.journal_entry:
		return
	entries = frappe.get_all(
		"Bank Transaction Payments",
		filters={"parent": row.bank_transaction},
		fields=["payment_document", "payment_entry"],
	)
	if any(entry.payment_document == "Sales Invoice" for entry in entries):
		return
	payments = [
		entry.payment_entry
		for entry in entries
		if entry.payment_document == "Payment Entry" and _is_submitted("Payment Entry", entry.payment_entry)
	]
	journals = [
		entry.payment_entry
		for entry in entries
		if entry.payment_document == "Journal Entry" and _is_submitted("Journal Entry", entry.payment_entry)
	]
	if len(payments) == 1 and not journals:
		row.payment_entry = payments[0]
	elif len(journals) == 1 and not payments:
		row.journal_entry = journals[0]


def _single_reconciled_journal_entry(bank_transaction):
	names = frappe.get_all(
		"Bank Transaction Payments",
		filters={"parent": bank_transaction, "payment_document": "Journal Entry"},
		pluck="payment_entry",
	)
	if len(names) == 1 and frappe.db.get_value("Journal Entry", names[0], "docstatus") == 1:
		return names[0]
	return None


def _debits_ready(doc, fee):
	debits = _debits_for(doc, fee)
	if not debits:
		return not flt(fee.fee_amount)
	if flt(sum(flt(row.amount) for row in debits), 2) != flt(fee.fee_amount, 2):
		return False
	return all(_bank_status(row.bank_transaction) == "Reconciled" for row in debits)


def _debits_for(doc, fee):
	return [row for row in doc.fee_debits if row.settlement_register_fee == fee.name]


def _bank_status(bank_transaction):
	if not bank_transaction:
		return None
	return frappe.db.get_value("Bank Transaction", bank_transaction, "status")


def _set_bullets(doc):
	settings = get_source_settings(doc.company, doc.source)
	create_payment = bool(settings and cint(settings.create_payment_if_missing))
	for row in doc.payments:
		if row.payment_entry or row.sales_invoice:
			row.row_bullet = "Green"
		elif (
			create_payment
			and row.customer
			and doc.clearing_account
			and flt(row.payment_amount)
			and not _is_reversal(row)
		):
			row.row_bullet = "Yellow"
		else:
			row.row_bullet = "Red"
	for row in doc.fees:
		if doc.source == "MAIB POS":
			row.row_bullet = "Green" if _debits_ready(doc, row) else "Red"
			continue
		if row.journal_entry or not flt(row.fee_amount):
			row.row_bullet = "Green"
		elif row.credit_date and flt(row.fee_amount) and doc.clearing_account and doc.fee_account:
			row.row_bullet = "Yellow"
		else:
			row.row_bullet = "Red"
	for row in doc.deposits:
		row.row_bullet = "Green" if _bank_status(row.bank_transaction) == "Reconciled" else "Red"


def _set_totals(doc):
	doc.total_payment = sum(flt(row.payment_amount) for row in doc.payments)
	doc.total_fee = sum(flt(row.fee_amount) for row in doc.payments)
	doc.total_net = sum(flt(row.net_amount) for row in doc.payments)


def _collapse_dated_rows(doc, table, date_field):
	kept = {}
	for row in list(doc.get(table)):
		if not row.get(date_field):
			doc.remove(row)
			continue
		credit_date = str(getdate(row.get(date_field)))
		if credit_date not in kept:
			kept[credit_date] = row
			continue
		if table == "fees":
			for debit in doc.fee_debits:
				if debit.settlement_register_fee == row.name:
					debit.settlement_register_fee = kept[credit_date].name
		doc.remove(row)
	return kept


def _sum_rows(rows, credit_date, field):
	return sum(flt(row.get(field)) for row in rows if str(getdate(row.transfer_date)) == credit_date)


def _filled_reference(row):
	for field in ("journal_entry", "payment_entry", "bank_transaction", "sales_invoice"):
		if row.get(field):
			return field, row.get(field)
	return None


def _is_reversal(row):
	return any(flt(row.get(field)) for field in ("reversal_amount", "reversal_cash_amount", "reversed_fee"))


_CANCELLED_LINK_FIELDS = {
	"Journal Entry": "journal_entry",
	"Payment Entry": "payment_entry",
}
_LINK_CHILD_TABLES = (
	"Settlement Register Payment",
	"Settlement Register Fee",
	"Settlement Register Fee Debit",
	"Settlement Register Deposit",
	"Settlement Register Reference",
)


def release_cancelled_document(doctype, name):
	field = _CANCELLED_LINK_FIELDS[doctype]
	parents = set()
	for child in _LINK_CHILD_TABLES:
		if not frappe.get_meta(child).has_field(field):
			continue
		parents.update(
			frappe.get_all(
				child,
				filters={"parenttype": "Settlement Register", field: name},
				pluck="parent",
			)
		)
	if doctype == "Journal Entry":
		register = frappe.db.get_value("Journal Entry", name, "settlement_register")
		if register:
			parents.add(register)
	for register in parents:
		_release_register_link(register, field, name)


def release_journal_links(register, journal_entry):
	_release_register_link(register, "journal_entry", journal_entry)


def _release_register_link(register, field, name):
	if not register or frappe.db.get_value("Settlement Register", register, "docstatus") != 1:
		return
	if ("Settlement Register", register) in frappe.flags.currently_saving:
		_clear_stored_links(register, field, name)
		return
	doc = frappe.get_doc("Settlement Register", register)
	_clear_doc_links(doc, field, name)
	_link_fee_payments(doc)
	_set_bullets(doc)
	sync_reference_rows(doc)
	doc.status = "Reconciled" if register_is_reconciled(doc) else "Unreconciled"
	_store_released_register(doc)


def _clear_doc_links(doc, field, name):
	for row in doc.payments:
		if row.get(field) != name:
			continue
		row.set(field, None)
		if field == "payment_entry":
			row.payment_created = 0
	for row in doc.fees:
		if row.get(field) != name:
			continue
		row.set(field, None)
		if field == "journal_entry":
			row.journal_created = 0
	for row in (*doc.fee_debits, *doc.deposits, *doc.reference_rows):
		if row.get(field) == name:
			row.set(field, None)


def _clear_stored_links(register, field, name):
	for child in _LINK_CHILD_TABLES:
		if not frappe.get_meta(child).has_field(field):
			continue
		for row_name in frappe.get_all(
			child,
			filters={"parent": register, field: name},
			pluck="name",
		):
			values = {field: None}
			if child == "Settlement Register Payment" and field == "payment_entry":
				values["payment_created"] = 0
			if child == "Settlement Register Fee" and field == "journal_entry":
				values["journal_created"] = 0
			frappe.db.set_value(child, row_name, values, update_modified=False)


def _store_released_register(doc):
	for row in doc.payments:
		frappe.db.set_value(
			row.doctype,
			row.name,
			{
				"payment_entry": row.payment_entry,
				"sales_invoice": row.sales_invoice,
				"payment_created": row.payment_created,
				"row_bullet": row.row_bullet,
			},
			update_modified=False,
		)
	for row in doc.fees:
		frappe.db.set_value(
			row.doctype,
			row.name,
			{
				"journal_entry": row.journal_entry,
				"journal_created": row.journal_created,
				"payment_entry": row.payment_entry,
				"external_number": row.external_number,
				"row_bullet": row.row_bullet,
			},
			update_modified=False,
		)
	for row in doc.fee_debits:
		frappe.db.set_value(row.doctype, row.name, "journal_entry", row.journal_entry, update_modified=False)
	for row in doc.deposits:
		frappe.db.set_value(
			row.doctype,
			row.name,
			{
				"payment_entry": row.payment_entry,
				"journal_entry": row.journal_entry,
				"row_bullet": row.row_bullet,
			},
			update_modified=False,
		)
	_replace_reference_rows(doc)
	frappe.db.set_value("Settlement Register", doc.name, "status", doc.status, update_modified=False)


def _cancel_linked(doctype, name):
	if not frappe.db.exists(doctype, name):
		return
	linked = frappe.get_doc(doctype, name)
	if linked.docstatus == 1:
		linked.flags.ignore_links = True
		linked.cancel()


def _normalize(value):
	return "".join(str(value or "").split()).casefold()
