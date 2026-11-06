# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import json

import frappe

SHORTCUT_LABEL = "Settlement Register"
ACCOUNTING_TITLE = "Accounting"


def ensure_accounting_shortcut():
	if not frappe.db.exists("DocType", "Workspace"):
		return
	if not frappe.db.exists("DocType", SHORTCUT_LABEL):
		return

	names = frappe.get_all("Workspace", filters={"title": ACCOUNTING_TITLE}, pluck="name")
	changed = False
	for name in names:
		if _add_shortcut(name):
			changed = True
	if changed:
		frappe.clear_cache()


def _add_shortcut(name):
	doc = frappe.get_doc("Workspace", name)
	content = json.loads(doc.content or "[]")
	has_row = any(row.label == SHORTCUT_LABEL and row.link_to == SHORTCUT_LABEL for row in doc.shortcuts)
	has_block = any(
		block.get("type") == "shortcut" and (block.get("data") or {}).get("shortcut_name") == SHORTCUT_LABEL
		for block in content
	)
	if has_row and has_block:
		return False

	if not has_row:
		doc.append(
			"shortcuts",
			{
				"type": "DocType",
				"link_to": SHORTCUT_LABEL,
				"label": SHORTCUT_LABEL,
			},
		)
	if not has_block:
		content.insert(
			_insert_at(content),
			{
				"id": "mdSettReg01",
				"type": "shortcut",
				"data": {"shortcut_name": SHORTCUT_LABEL, "col": 3},
			},
		)
		doc.content = json.dumps(content, ensure_ascii=False)

	# Public save in developer mode exports the Accounting workspace into ERPNext.
	previous = frappe.flags.in_patch
	frappe.flags.in_patch = True
	try:
		doc.save(ignore_permissions=True)
	finally:
		frappe.flags.in_patch = previous
	return True


def _insert_at(content):
	for index, block in enumerate(content):
		data = block.get("data") or {}
		if block.get("type") == "shortcut" and data.get("shortcut_name") == "Payment Entry":
			return index + 1
	last_shortcut = None
	for index, block in enumerate(content):
		if block.get("type") == "shortcut":
			last_shortcut = index
	if last_shortcut is None:
		return len(content)
	return last_shortcut + 1
