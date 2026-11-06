frappe.ui.form.on("Settlements Source", {
	source(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.source === "MAIB POS") {
			row.create_payment_if_missing = 0;
			frm.refresh_field("sources");
		}
	},
});
