# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

"""Read the first relevant worksheet of an xlsx file without openpyxl."""

import re
import zipfile
from xml.etree import ElementTree

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_COL = re.compile(r"[A-Z]+")


def worksheet_rows(path, preferred_sheet=None):
	"""Return a list of {column letter: cell text} for each occupied row."""
	with zipfile.ZipFile(path) as book:
		shared = _shared_strings(book)
		sheet_path = _sheet_path(book, preferred_sheet)
		root = ElementTree.fromstring(book.read(sheet_path))
	rows = []
	for row in root.findall("m:sheetData/m:row", NS):
		cells = {}
		for cell in row.findall("m:c", NS):
			ref = cell.get("r") or ""
			column = _COL.match(ref)
			if not column:
				continue
			value = cell.find("m:v", NS)
			if value is None or value.text is None:
				text = ""
			elif cell.get("t") == "s":
				text = shared[int(value.text)]
			else:
				text = value.text
			cells[column.group(0)] = text
		if any(str(text).strip() for text in cells.values()):
			rows.append(cells)
	return rows


def _shared_strings(book):
	name = next((item for item in book.namelist() if item.lower().endswith("sharedstrings.xml")), None)
	if not name:
		return []
	root = ElementTree.fromstring(book.read(name))
	strings = []
	node = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
	for item in root.findall("m:si", NS):
		strings.append("".join(part.text or "" for part in item.iter(node)))
	return strings


def _sheet_path(book, preferred_sheet):
	root = ElementTree.fromstring(book.read("xl/workbook.xml"))
	rels = ElementTree.fromstring(book.read("xl/_rels/workbook.xml.rels"))
	targets = {}
	for rel in rels:
		targets[rel.get("Id")] = rel.get("Target")
	chosen = None
	for sheet in root.findall("m:sheets/m:sheet", NS):
		target = targets.get(sheet.get(_REL))
		if not target:
			continue
		path = target if target.startswith("xl/") else "xl/" + target.lstrip("/")
		if preferred_sheet and sheet.get("name") == preferred_sheet:
			return path
		if chosen is None:
			chosen = path
	if not chosen:
		raise ValueError("The workbook has no worksheet.")
	return chosen
