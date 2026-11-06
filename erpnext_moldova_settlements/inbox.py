# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe

from erpnext_moldova_settlements.moldova_settlements.parsers.register_file import (
	AutorizatReport,
	RegisterFileError,
	parse_register_file,
)
from erpnext_moldova_settlements.moldova_settlements.register import active_register_name


def handle_inbound_email(inbound_email):
	"""Create a settlement register from a supplier email. Return None when the message is not ours."""
	if not frappe.db.exists("DocType", "Supplier Inbox Email"):
		return None
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Supplier Inbox Email", "attached_to_name": inbound_email},
		fields=["file_name", "file_url"],
	)
	created = None
	for row in files:
		file_doc = frappe.db.get_value("File", {"file_url": row.file_url}, "name")
		if not file_doc:
			continue
		path = frappe.get_doc("File", file_doc).get_full_path()
		try:
			parsed = parse_register_file(path, row.file_name)
		except AutorizatReport:
			continue
		except RegisterFileError:
			continue
		existing = active_register_name(parsed["register_number"])
		if existing:
			created = created or existing
			continue
		doc = frappe.new_doc("Settlement Register")
		doc.source_file = row.file_url
		doc.supplier_inbox_email = inbound_email
		doc.insert(ignore_permissions=True)
		created = doc.name
	if not created:
		return None
	return {"doctype": "Settlement Register", "name": created}
