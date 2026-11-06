frappe.ui.form.on("Settlement Register", {
	refresh(frm) {
		show_fields(frm);
		set_row_indicators(frm);
		set_payment_queries(frm);
		lock_linked_customers(frm);
		if (frm.doc.docstatus === 2) {
			return;
		}
		if (frm.doc.name) {
			frm.set_query("settlement_register_fee", "fee_debits", () => ({
				filters: {parent: frm.doc.name},
			}));
		}
		if (frm.doc.source === "MAIB POS") {
			frm.add_custom_button(
				__("Identify Fee Bank Transactions"),
				() => run_action(frm, "identify_fee_debits"),
				__("Actions")
			);
			frm.add_custom_button(
				__("Identify Deposit Bank Transactions"),
				() => run_action(frm, "identify_deposits"),
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
					() => run_action(frm, "identify_payments"),
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

frappe.ui.form.on("Settlement Register Payment", {
	form_render(frm, cdt, cdn) {
		lock_customer(frm, cdt, cdn);
	},
	payment_entry(frm, cdt, cdn) {
		fill_customer_from_link(frm, cdt, cdn);
		refresh_payment_indicator(frm, cdn);
	},
	sales_invoice(frm, cdt, cdn) {
		fill_customer_from_link(frm, cdt, cdn);
		refresh_payment_indicator(frm, cdn);
	},
});

function show_fields(frm) {
	const maibPos = frm.doc.source === "MAIB POS";
	frm.toggle_display("bank_account", maibPos);
	frm.toggle_display("fee_account", !maibPos);
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

function refresh_payment_indicator(frm, cdn) {
	const grid = frm.fields_dict.payments && frm.fields_dict.payments.grid;
	const grid_row = grid && grid.grid_rows_by_docname && grid.grid_rows_by_docname[cdn];
	if (grid_row) {
		grid_row.refresh_field("external_number");
	}
}

function indicator_color(table, doc) {
	if (table === "payments" && doc && (doc.payment_entry || doc.sales_invoice)) {
		return "green";
	}
	return {Green: "green", Yellow: "yellow", Red: "red"}[doc && doc.row_bullet] || "gray";
}

function set_row_indicators(frm) {
	[
		["payments", "Settlement Register Payment", "external_number"],
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
