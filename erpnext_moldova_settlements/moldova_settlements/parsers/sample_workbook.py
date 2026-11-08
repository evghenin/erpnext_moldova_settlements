# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

"""Fictional register workbooks for tests. Nothing here is taken from a live file."""

import tempfile
from datetime import date
from html import escape
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

_ROOT = Path(tempfile.mkdtemp(prefix="settlement-fixtures-"))


def novapay_file(number, payments):
	rows = [
		{"B": "РЕЕСТР ПЕРЕВОДОВ"},
		{"B": "Получатель:", "E": "Sample Merchant SRL"},
		{"B": "Дата:", "E": "02.02.2026"},
		{
			"B": "№",
			"C": "Дата перечисления средств",
			"D": "Дата приема средств",
			"E": "Сумма принятого платежа",
			"F": "Сумма удержанного вознаграждения",
			"G": "Сума к перечислению",
			"H": "ФИО Покупателя",
			"I": "№ ЕН",
		},
	]
	for index, payment in enumerate(payments, start=1):
		rows.append(
			{
				"B": str(index),
				"C": payment.get("transfer", "15.06.2026"),
				"D": payment.get("receipt", "14.06.2026"),
				"E": payment["payment"],
				"F": payment["fee"],
				"G": payment["net"],
				"H": payment.get("payer", "Alex Sample"),
				"I": payment["external"],
			}
		)
	rows.append({"B": "Всего:"})
	return _write(f"Реестр платежей №{number}.XLSX", rows)


def megamega_file():
	rows = [
		{"B": "РЕЕСТР ПЕРЕВОДОВ ОТ MEGAMEGA COMPANY SRL"},
		{"B": "Получатель:", "E": '"Sample Merchant" S.R.L'},
		{"B": "Дата:", "E": str(_serial(date(2026, 7, 6)))},
		{
			"B": "№",
			"C": " Дата приема средств",
			"D": "Дата перечисления средств",
			"E": "Сумма принятого платежа",
			"F": "Сумма удержанного вознаграждения",
			"G": "Сумма к перечислению",
		},
		{
			"B": "1",
			"C": str(_serial(date(2026, 6, 17))),
			"D": str(_serial(date(2026, 7, 6))),
			"E": "100",
			"F": "12.996000000000002",
			"G": "87.004000000000002",
		},
		{"B": "Всего:"},
	]
	return _write("Реестр платежей.XLSX", rows)


def pos_month_file(filename):
	rows = [
		{
			"A": (
				"Raport privind sumele transferate si comisionul retinut "
				"pentru intervalul 2026-09-01-2026-09-30"
			)
		},
		{"A": "Sample Merchant SmartPOS"},
		_maib_header(ecomm=False),
		_maib_payment(
			"1",
			"S1000001",
			"RRN-POS-1",
			"2026-09-01 09:00:00",
			"2026-09-02",
			"100",
			"1.50",
			"98.50",
		),
		_maib_payment(
			"2",
			"S1000001",
			"RRN-POS-2",
			"2026-09-30 18:00:00",
			"2026-10-01",
			"40",
			"0.50",
			"39.50",
		),
		{"B": "Total"},
	]
	return _write(filename, rows)


def ecomm_daily_file(filename):
	rows = [
		{
			"A": (
				"Raport privind sumele transferate si comisionul retinut "
				"pentru intervalul 20260909-20260909"
			)
		},
		{"A": "Ecomm Sample Merchant"},
		_maib_header(ecomm=True),
		_maib_payment(
			"1",
			"E1000001",
			"RRN-SAMPLE-1",
			"2026-09-08 10:00:00",
			"2026-09-09",
			"100",
			"2.50",
			"97.00",
			authorization_fee="0.50",
		),
		{"B": "Total"},
	]
	return _write(filename, rows)


def ecomm_month_file(filename):
	rows = [
		{
			"A": (
				"Raport privind sumele transferate si comisionul retinut "
				"pentru intervalul 2026-10-01-2026-10-31"
			)
		},
		{"A": "Ecomm Sample Merchant"},
		_maib_header(ecomm=True),
		_maib_payment(
			"1",
			"E1000001",
			"RRN-SAMPLE-2",
			"2026-10-02 11:00:00",
			"2026-10-03",
			"80",
			"2.00",
			"77.00",
			authorization_fee="1.00",
		),
		{"B": "Total"},
	]
	return _write(filename, rows)


def _maib_header(ecomm):
	labels = [
		"Nr",
		"TerminalID",
		"ReferintaTranzactiei",
		"NumeTerminal",
		"DataTranzactiei",
		"DataTransferului",
		"Tip_Tranzactie",
		"Valuta",
		"NrCARD",
		"SumaTranzactiei",
		"Commission",
	]
	if ecomm:
		labels.append("ComisAuth")
	labels.extend(
		[
			"SumaNumerar",
			"Suma_net",
			"SumaReversa",
			"ReversSumaNumerar",
			"ComisionReversat",
			"Instant_Discount",
		]
	)
	return {_column(index): label for index, label in enumerate(labels)}


def _maib_payment(
	number,
	terminal,
	reference,
	paid_at,
	transfer_date,
	payment,
	commission,
	net,
	authorization_fee=None,
):
	values = [
		number,
		terminal,
		reference,
		"shop.example.test",
		paid_at,
		transfer_date,
		"Local",
		"MDL",
		"0000**00",
		payment,
		commission,
	]
	if authorization_fee is not None:
		values.append(authorization_fee)
	values.extend(["0", net, "0", "0", "0", "0"])
	return {_column(index): value for index, value in enumerate(values)}


def _column(index):
	letters = ""
	index += 1
	while index:
		index, remainder = divmod(index - 1, 26)
		letters = chr(65 + remainder) + letters
	return letters


def _serial(day):
	return (day - date(1899, 12, 30)).days


def _write(filename, rows):
	path = _ROOT / filename
	path.parent.mkdir(parents=True, exist_ok=True)
	sheet_rows = []
	for index, cells in enumerate(rows, start=1):
		written = []
		for column, value in cells.items():
			text = escape(str(value), quote=False)
			written.append(f'<c r="{column}{index}"><v>{text}</v></c>')
		sheet_rows.append(f'<row r="{index}">{"".join(written)}</row>')
	sheet = (
		'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
		'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
		f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
	)
	workbook = (
		'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
		'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
		'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
		'<sheets><sheet name="MDL" sheetId="1" r:id="rId1"/></sheets></workbook>'
	)
	rels = (
		'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
		'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
		'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
		'Target="worksheets/sheet1.xml"/></Relationships>'
	)
	package = (
		'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
		'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
		'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
		'Target="xl/workbook.xml"/></Relationships>'
	)
	types = (
		'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
		'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
		'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
		'<Default Extension="xml" ContentType="application/xml"/>'
		'<Override PartName="/xl/workbook.xml" '
		'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
		'<Override PartName="/xl/worksheets/sheet1.xml" '
		'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
		"</Types>"
	)
	with ZipFile(path, "w", ZIP_DEFLATED) as book:
		book.writestr("[Content_Types].xml", types)
		book.writestr("_rels/.rels", package)
		book.writestr("xl/workbook.xml", workbook)
		book.writestr("xl/_rels/workbook.xml.rels", rels)
		book.writestr("xl/worksheets/sheet1.xml", sheet)
	return path
