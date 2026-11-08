# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

"""Turn a supplier file into register fields. No Frappe import: safe to run on samples."""

import hashlib
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from erpnext_moldova_settlements.moldova_settlements.parsers.xlsx import worksheet_rows

MONEY = Decimal("0.01")
CARD_FEE_DESCRIPTION = "Retinerea comisionului-operatiunile acceptare card"
CARD_DEPOSIT_DESCRIPTION = "Transfer pentru operatiuni de acceptare a cardurilor"
DEPOSIT_PATTERNS = {
	"NovaPay": "PLATA PENTRU RAMBURS",
	"MegaMega": "Conform contractul",
	"MAIB POS": CARD_DEPOSIT_DESCRIPTION,
	"MAIB Ecomm": "Transfer pentru operatiuni de acceptare a cardurilor la plata Ecomm",
}


class SettledMonthReport(Exception):
	"""The monthly settled report follows transfer dates, not the days customers paid."""


class RegisterFileError(Exception):
	pass


class AmountMismatch(RegisterFileError):
	def __init__(self, label, payment, fee, net):
		self.label = label
		self.payment = payment
		self.fee = fee
		self.net = net
		super().__init__(
			f"File amounts do not match on row {label}: payment {payment}, fee {fee}, net {net}."
		)


class UnreadableDate(RegisterFileError):
	def __init__(self, text):
		self.text = text
		super().__init__(f"Cannot read the date {text}.")


class UnreadableTime(RegisterFileError):
	def __init__(self, text):
		self.text = text
		super().__init__(f"Cannot read the transaction time {text}.")


def parse_register_file(path, filename):
	name = filename or ""
	lower = name.lower()
	if lower.endswith(".csv"):
		raise RegisterFileError("This file is not a settlement register.")
	if _monthly_settled_name(lower):
		raise SettledMonthReport("The monthly settled report does not create a register.")

	rows = worksheet_rows(path, preferred_sheet="MDL")
	text = "\n".join(" ".join(row.values()) for row in rows[:12])
	if "TerminalID" in text and "DataTransferului" in text:
		return _parse_maib(rows, name)
	if "MEGAMEGA" in text.upper():
		return _parse_transfer_sheet(rows, name, "MegaMega")
	if "РЕЕСТР ПЕРЕВОДОВ" in text.upper():  # noqa: RUF001
		return _parse_transfer_sheet(rows, name, "NovaPay")
	raise RegisterFileError("The file is not a NovaPay, MegaMega, or MAIB POS register.")


def _parse_transfer_sheet(rows, filename, source):
	header_at = next((index for index, row in enumerate(rows) if _clean(row.get("B")) == "№"), None)
	if header_at is None:
		raise RegisterFileError("The payment table was not found.")
	columns = _transfer_columns(rows[header_at])
	payments = []
	for row in rows[header_at + 1 :]:
		marker = _clean(row.get("B"))
		if not marker or marker.startswith("Всего"):  # noqa: RUF001
			break
		payment = _money(row.get(columns["payment"]))
		fee = _money(row.get(columns["fee"]))
		net = _money(row.get(columns["net"]))
		_check_identity(marker, payment, fee, net)
		payments.append(
			{
				"row_number": marker,
				"transfer_date": _date(row.get(columns["transfer"])),
				"payment_date": _date(row.get(columns["receipt"])),
				"payment_amount": payment,
				"fee_amount": fee,
				"net_amount": net,
				"payer_name": _clean(row.get(columns.get("payer"))) if columns.get("payer") else "",
				"external_number": _clean(row.get(columns.get("external"))) if columns.get("external") else "",
			}
		)
	if not payments:
		raise RegisterFileError("The register has no payment rows.")
	header_date = _header_date(rows)
	return {
		"source": source,
		"register_number": _transfer_number(source, filename, payments),
		"posting_date": header_date or payments[0]["transfer_date"],
		"currency": None,
		"shipment_numbers": [row["external_number"] for row in payments if row["external_number"]],
		"payments": payments,
	}


def _transfer_columns(header):
	found = {}
	for column, value in header.items():
		label = _clean(value).casefold()
		if "перечислен" in label and "дат" in label:
			found["transfer"] = column
		elif "прием" in label and "дат" in label:
			found["receipt"] = column
		elif "принятого" in label:
			found["payment"] = column
		elif "вознагражд" in label:
			found["fee"] = column
		elif "перечислен" in label:
			found["net"] = column
		elif "фио" in label:
			found["payer"] = column
		elif "ен" in label:
			found["external"] = column
	missing = {"transfer", "receipt", "payment", "fee", "net"} - set(found)
	if missing:
		raise RegisterFileError("The payment table is missing columns.")
	return found


def _header_date(rows):
	for row in rows:
		if _clean(row.get("B")).startswith("Дата"):
			return _date(row.get("E"))
	return None


def _transfer_number(source, filename, payments):
	if source == "NovaPay":
		match = re.search(r"№\s*(\d+)", filename or "")
		if match:
			return f"NP-{match.group(1)}"
		digest = hashlib.sha1("\n".join(sorted(row["external_number"] for row in payments)).encode()).hexdigest()
		return f"NP-{digest[:12]}"
	row = payments[0]
	amount = format(row["payment_amount"], "f")
	return f"MM-{row['transfer_date']}-{amount}-{row['payment_date']}"


def _monthly_settled_name(filename):
	"""POS and Ecomm use the same names: lunar decontat is the settled month."""
	name = (filename or "").lower()
	return "autorizat" not in name and "lunar" in name and "decontat" in name


def _parse_maib(rows, filename):
	title = _clean(rows[0].get("A") if rows else "")
	period = _report_period(title)
	if not period:
		raise RegisterFileError("The MAIB POS report has no transfer period.")
	if _settled_month(filename, period):
		raise SettledMonthReport("The monthly settled report does not create a register.")
	header_at = next(
		(
			index
			for index, row in enumerate(rows)
			if _clean(row.get("A")) == "Nr" and _clean(row.get("B")) == "TerminalID"
		),
		None,
	)
	if header_at is None:
		raise RegisterFileError("The MAIB POS payment table was not found.")
	columns = { _clean(value): column for column, value in rows[header_at].items() }
	ecomm = "ComisAuth" in columns
	payments = []
	for row in rows[header_at + 1 :]:
		if _clean(row.get("B")) in {"Total", ""} and not _clean(row.get("C")):
			break
		if not _clean(row.get(columns.get("ReferintaTranzactiei", "C"))):
			break
		payment = _money(row.get(columns["SumaTranzactiei"]))
		fee = _money(row.get(columns["Commission"]))
		if ecomm:
			fee += _money(row.get(columns["ComisAuth"]))
		net = _money(row.get(columns["Suma_net"]))
		reference = _clean(row.get(columns["ReferintaTranzactiei"]))
		_check_identity(reference, payment, fee, net)
		paid_at = _datetime(row.get(columns["DataTranzactiei"]))
		if not paid_at:
			raise RegisterFileError("A payment row has no date.")
		payments.append(
			{
				"row_number": _clean(row.get(columns["Nr"])),
				"terminal_id": _clean(row.get(columns["TerminalID"])),
				"external_number": reference,
				"terminal_name": _clean(row.get(columns["NumeTerminal"])),
				"transaction_datetime": paid_at,
				"payment_date": paid_at[:10],
				"transfer_date": _date(row.get(columns["DataTransferului"])),
				"transaction_type": _clean(row.get(columns["Tip_Tranzactie"])),
				"valuta": _clean(row.get(columns["Valuta"])),
				"card_number": _clean(row.get(columns["NrCARD"])),
				"payment_amount": payment,
				"fee_amount": fee,
				"cash_amount": _money(row.get(columns["SumaNumerar"])),
				"net_amount": net,
				"reversal_amount": _money(row.get(columns["SumaReversa"])),
				"reversal_cash_amount": _money(row.get(columns["ReversSumaNumerar"])),
				"reversed_fee": _money(row.get(columns["ComisionReversat"])),
				"instant_discount": _money(row.get(columns["Instant_Discount"])),
			}
		)
	if not payments:
		raise RegisterFileError("The MAIB POS report has no payment rows.")
	terminal = payments[0]["terminal_id"]
	currencies = {row["valuta"] for row in payments if row["valuta"]}
	if len(currencies) != 1:
		raise RegisterFileError("The MAIB POS report must use one currency.")
	return {
		"source": "MAIB Ecomm" if ecomm else "MAIB POS",
		"register_number": f"MAIB-{terminal}-{period[0]}-{period[1]}",
		"posting_date": _maib_register_date(filename, period),
		"currency": next(iter(currencies)),
		"shipment_numbers": [row["external_number"] for row in payments],
		"payments": payments,
	}


def _settled_month(filename, period):
	"""A report longer than one day is the month. POS and Ecomm load it only from autorizat."""
	name = (filename or "").lower()
	if "autorizat" in name or period[0] == period[1]:
		return False
	return True


def _maib_register_date(filename, period):
	"""Report date from the file name (autorizatYYYYMMDD or decontatYYYYMMDD). Otherwise the period end."""
	match = re.search(r"(?:autorizat|decontat)(\d{8})", (filename or "").lower())
	if match:
		try:
			return datetime.strptime(match.group(1), "%Y%m%d").date().isoformat()
		except ValueError:
			pass
	return period[1]


def _report_period(title):
	dashed = re.search(r"(\d{4}-\d{2}-\d{2})-(\d{4}-\d{2}-\d{2})", title)
	if dashed:
		return dashed.group(1), dashed.group(2)
	compact = re.search(r"(\d{8})-(\d{8})", title)
	if not compact:
		return None
	try:
		start = datetime.strptime(compact.group(1), "%Y%m%d").date().isoformat()
		end = datetime.strptime(compact.group(2), "%Y%m%d").date().isoformat()
	except ValueError:
		return None
	return start, end


def _check_identity(label, payment, fee, net):
	if payment != fee + net:
		raise AmountMismatch(label, payment, fee, net)


def _money(value):
	text = _clean(value)
	if not text:
		return Decimal("0.00")
	return Decimal(text).quantize(MONEY, rounding=ROUND_HALF_UP)


def _date(value):
	text = _clean(value)
	if not text:
		raise RegisterFileError("A payment row has no date.")
	for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
		try:
			return datetime.strptime(text[:10], fmt).date().isoformat()
		except ValueError:
			continue
	if re.fullmatch(r"\d+(\.0+)?", text):
		serial = int(float(text))
		return (date(1899, 12, 30) + timedelta(days=serial)).isoformat()
	raise UnreadableDate(text)


def _datetime(value):
	text = _clean(value)
	if not text:
		return None
	for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
		try:
			return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M:%S")
		except ValueError:
			continue
	raise UnreadableTime(text)


def _clean(value):
	return str(value or "").strip()
