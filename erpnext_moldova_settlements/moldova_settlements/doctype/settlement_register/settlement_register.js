frappe.ui.form.on("Settlement Register", {
	refresh(frm) {
		frm.ignore_doctypes_on_cancel_all = ["Journal Entry", "Payment Entry"];
		const submitted = frm.doc.docstatus > 0;
		frm.set_df_property("payments", "cannot_add_rows", submitted);
		frm.set_df_property("payments", "cannot_delete_rows", submitted);
		show_fields(frm);
		set_row_indicators(frm);
		set_payment_queries(frm);
		set_invoice_query(frm);
		frm.set_query("bank_account", () => ({
			filters: {company: frm.doc.company},
		}));
		lock_linked_customers(frm);
		if (frm.doc.docstatus === 2) {
			return;
		}
		if (frm.doc.name) {
			frm.set_query("settlement_register_fee", "fee_debits", () => ({
				filters: {parent: frm.doc.name},
			}));
		}
		if (frm.doc.source) {
			frm.add_custom_button(
				__("Identify Deposit Bank Transactions"),
				() => run_identify(frm, "identify_deposits"),
				__("Actions")
			);
		}
		if (frm.doc.source === "MAIB POS") {
			frm.add_custom_button(
				__("Identify Fee Bank Transactions"),
				() => run_identify(frm, "identify_fee_debits"),
				__("Actions")
			);
		}
		if (frm.doc.source === "NovaPay" || frm.doc.source === "MegaMega") {
			frm.add_custom_button(
				__("Identify Commission Invoices"),
				() => run_identify(frm, "identify_fee_invoices"),
				__("Actions")
			);
		}
		if (!frm.doc.company || !frm.doc.source) {
			return;
		}
		frappe.db.get_doc("Settlements Settings", "Settlements Settings").then((settings) => {
			const row = (settings.sources || []).find(
				(source) => source.company === frm.doc.company && source.source === frm.doc.source
			);
			if (!row) {
				return;
			}
			if (row.search_payments) {
				frm.add_custom_button(
					__("Identify Payment Documents"),
					() => run_identify(frm, "identify_payments"),
					__("Actions")
				);
			}
			if (frm.doc.docstatus === 1 && row.create_payment_if_missing) {
				frm.add_custom_button(
					__("Create Missing Payments"),
					() => run_action(frm, "create_missing_payments"),
					__("Actions")
				);
			}
		});
	},
	source(frm) {
		show_fields(frm);
	},
});

frappe.ui.form.on("Settlement Register Fee", {
	purchase_invoice(frm, cdt, cdn) {
		refresh_row_indicator(frm, "fees", cdn, "credit_date");
	},
	journal_entry(frm, cdt, cdn) {
		refresh_row_indicator(frm, "fees", cdn, "credit_date");
	},
});

frappe.ui.form.on("Settlement Register Payment", {
	form_render(frm, cdt, cdn) {
		lock_customer(frm, cdt, cdn);
	},
	payment_entry(frm, cdt, cdn) {
		fill_customer_from_link(frm, cdt, cdn);
		refresh_row_indicator(frm, "payments", cdn, "payment_date");
	},
	sales_invoice(frm, cdt, cdn) {
		fill_customer_from_link(frm, cdt, cdn);
		refresh_row_indicator(frm, "payments", cdn, "payment_date");
	},
});

function show_fields(frm) {
	frm.toggle_display("bank_account", true);
	frm.toggle_display("fee_account", frm.doc.source !== "MAIB POS");
	const grid = frm.fields_dict.fees && frm.fields_dict.fees.grid;
	if (!grid || !grid.update_docfield_property) {
		return;
	}
	const show_invoice = frm.doc.source === "NovaPay" || frm.doc.source === "MegaMega";
	grid.update_docfield_property("purchase_invoice", "hidden", show_invoice ? 0 : 1);
}

function set_invoice_query(frm) {
	if (frm.doc.source !== "NovaPay" && frm.doc.source !== "MegaMega") {
		return;
	}
	frm.set_query("purchase_invoice", "fees", () => ({
		query: "erpnext_moldova_settlements.moldova_settlements.doctype.settlement_register.settlement_register.commission_invoice_query",
		filters: {
			company: frm.doc.company,
			source: frm.doc.source,
			currency: frm.doc.currency,
		},
	}));
}

function set_payment_queries(frm) {
	frm.set_query("payment_entry", "payments", (doc, cdt, cdn) => {
		const row = locals[cdt][cdn];
		const filters = {
			company: doc.company,
			docstatus: 1,
			payment_type: "Receive",
		};
		if (row.customer) {
			filters.party = row.customer;
		}
		return {filters};
	});
	frm.set_query("sales_invoice", "payments", (doc, cdt, cdn) => {
		const row = locals[cdt][cdn];
		const filters = {
			company: doc.company,
			docstatus: 1,
			is_pos: 1,
		};
		if (row.customer) {
			filters.customer = row.customer;
		}
		return {filters};
	});
}

function fill_customer_from_link(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	lock_customer(frm, cdt, cdn);
	if (row.customer || (!row.payment_entry && !row.sales_invoice)) {
		return;
	}
	if (row.payment_entry) {
		frappe.db.get_value("Payment Entry", row.payment_entry, ["party_type", "party"]).then((r) => {
			const value = r.message || {};
			if (value.party_type === "Customer" && value.party) {
				frappe.model.set_value(cdt, cdn, "customer", value.party);
			}
		});
		return;
	}
	frappe.db.get_value("Sales Invoice", row.sales_invoice, "customer").then((r) => {
		if (r.message && r.message.customer) {
			frappe.model.set_value(cdt, cdn, "customer", r.message.customer);
		}
	});
}

function lock_linked_customers(frm) {
	(frm.doc.payments || []).forEach((row) => lock_customer(frm, row.doctype, row.name));
}

function lock_customer(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const grid = frm.fields_dict.payments && frm.fields_dict.payments.grid;
	if (!row || !grid || !grid.grid_rows_by_docname) {
		return;
	}
	const grid_row = grid.grid_rows_by_docname[cdn];
	if (!grid_row) {
		return;
	}
	grid_row.toggle_editable("customer", !(row.payment_entry || row.sales_invoice));
}

function run_identify(frm, method) {
	frappe.call({
		method: `erpnext_moldova_settlements.moldova_settlements.doctype.settlement_register.settlement_register.${method}`,
		args: {doc: frm.doc},
		freeze: true,
		callback(r) {
			apply_identified(frm, r.message || {});
		},
	});
}

function apply_identified(frm, message) {
	const filled =
		(message.fee_debits || []).length +
		count_new_links(frm, "payments", message.payments, ["payment_entry", "sales_invoice"]) +
		count_new_links(frm, "deposits", message.deposits, ["bank_transaction"]) +
		count_new_links(frm, "fees", message.fees, ["purchase_invoice", "journal_entry"]);
	const assignments = [];
	collect_assignments(frm, assignments, "payments", message.payments, [
		"customer",
		"row_bullet",
		"payment_entry",
		"sales_invoice",
	]);
	collect_assignments(frm, assignments, "deposits", message.deposits, [
		"row_bullet",
		"bank_transaction",
		"payment_entry",
		"journal_entry",
	]);
	collect_assignments(frm, assignments, "fees", message.fees, [
		"row_bullet",
		"journal_entry",
		"purchase_invoice",
	]);
	for (const incoming of message.fee_debits || []) {
		frm.add_child("fee_debits", {
			settlement_register_fee: incoming.settlement_register_fee,
			amount: incoming.amount,
			bank_transaction: incoming.bank_transaction,
			journal_entry: incoming.journal_entry,
			currency: incoming.currency || frm.doc.currency,
		});
	}
	if (message.fee_debits && message.fee_debits.length) {
		frm.dirty();
		frm.refresh_field("fee_debits");
	}
	const apply_next = () => {
		const next = assignments.shift();
		if (!next) {
			set_row_indicators(frm);
			lock_linked_customers(frm);
			frappe.show_alert({
				message: filled
					? __("Filled {0} rows in the form. Save the register to keep them.", [filled])
					: __("Nothing matched."),
				indicator: filled ? "green" : "orange",
			});
			return;
		}
		frappe.model.set_value(next.doctype, next.name, next.field, next.value).then(apply_next);
	};
	apply_next();
}

function count_new_links(frm, table, rows, fields) {
	let count = 0;
	for (const incoming of rows || []) {
		const row = (frm.doc[table] || []).find((item) => item.name === incoming.name);
		if (!row) {
			continue;
		}
		if (fields.some((field) => incoming[field] && incoming[field] !== row[field])) {
			count += 1;
		}
	}
	return count;
}

function collect_assignments(frm, assignments, table, rows, fields) {
	for (const incoming of rows || []) {
		const row = (frm.doc[table] || []).find((item) => item.name === incoming.name);
		if (!row) {
			continue;
		}
		for (const field of fields) {
			if (field !== "row_bullet" && !incoming[field]) {
				continue;
			}
			const value = incoming[field] || "";
			if ((row[field] || "") === value) {
				continue;
			}
			assignments.push({doctype: row.doctype, name: row.name, field, value});
		}
	}
}

function run_action(frm, method) {
	const call = () => {
		frappe.call({
			method: `erpnext_moldova_settlements.moldova_settlements.doctype.settlement_register.settlement_register.${method}`,
			args: {name: frm.doc.name},
			freeze: true,
			callback() {
				frm.reload_doc();
			},
		});
	};
	if (frm.is_dirty() || frm.is_new()) {
		frm.save().then(call);
		return;
	}
	call();
}

function refresh_row_indicator(frm, table, cdn, fieldname) {
	const grid = frm.fields_dict[table] && frm.fields_dict[table].grid;
	const grid_row = grid && grid.grid_rows_by_docname && grid.grid_rows_by_docname[cdn];
	if (grid_row) {
		grid_row.refresh_field(fieldname);
	}
}

function indicator_color(table, doc) {
	if (table === "payments" && doc && (doc.payment_entry || doc.sales_invoice)) {
		return "green";
	}
	if (table === "fees" && doc && (doc.purchase_invoice || doc.journal_entry)) {
		return "green";
	}
	return {Green: "green", Yellow: "yellow", Red: "red"}[doc && doc.row_bullet] || "gray";
}

function set_row_indicators(frm) {
	[
		["payments", "Settlement Register Payment", "payment_date"],
		["fees", "Settlement Register Fee", "credit_date"],
		["deposits", "Settlement Register Deposit", "credit_date"],
	].forEach(([table, doctype, fieldname]) => {
		const formatter = (value, field, options, doc) => {
			const color = indicator_color(table, doc);
			const label = !value
				? ""
				: field.fieldtype === "Date"
					? frappe.datetime.str_to_user(value)
					: value;
			return `<span class="indicator ${color}">${frappe.utils.escape_html(label)}</span>`;
		};
		const meta = frappe.meta.get_docfield(doctype, fieldname);
		if (meta) {
			meta.formatter = formatter;
		}
		if (frm.doc && frm.doc.name) {
			frappe.meta.set_formatter(doctype, fieldname, frm.doc.name, formatter);
		}
		const grid = frm.fields_dict[table] && frm.fields_dict[table].grid;
		if (!grid) {
			return;
		}
		const apply = (df) => {
			if (df && df.fieldname === fieldname) {
				df.formatter = formatter;
			}
		};
		(grid.docfields || []).forEach(apply);
		(grid.user_defined_columns || []).forEach(apply);
		(grid.grid_rows || []).forEach((row) => (row.docfields || []).forEach(apply));
		if (grid.fields_map) {
			apply(grid.fields_map[fieldname]);
		}
		grid.refresh();
	});
}
