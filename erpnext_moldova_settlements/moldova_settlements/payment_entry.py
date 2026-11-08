# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt


def before_cancel(doc, method=None):
	from erpnext_moldova_settlements.moldova_settlements.register import release_cancelled_document

	release_cancelled_document("Payment Entry", doc.name)
