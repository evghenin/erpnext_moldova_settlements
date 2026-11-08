# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import frappe

from erpnext_moldova_settlements.moldova_settlements.parsers.register_file import (
	AutorizatReport,
	RegisterFileError,
	parse_register_file,
)
from erpnext_moldova_settlements.moldova_settlements.register import active_register_name

HANDLER = "erpnext_moldova_settlements.inbox.handle_inbound_email"


def release_inbox_handler(register_name, *, clear_reference):
	"""Queue the inbox row again so the next run can store a new register.

	Delete checks the dynamic link after on_trash, so a draft has to drop it
	first. Cancel is not blocked by that row, and the old name stays until the
	handler writes the new register.
	"""
	if not frappe.db.exists("DocType", "Supplier Inbox Email Handler"):
		return
	names = frappe.get_all(
		"Supplier Inbox Email Handler",
		filters={
			"handler": HANDLER,
			"reference_doctype": "Settlement Register",
			"reference_name": register_name,
		},
		pluck="name",
	)
	for name in names:
		values = {"status": "Queued", "error": None}
		if clear_reference:
			values["reference_doctype"] = None
			values["reference_name"] = None
		frappe.db.set_value("Supplier Inbox Email Handler", name, values, update_modified=False)


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
