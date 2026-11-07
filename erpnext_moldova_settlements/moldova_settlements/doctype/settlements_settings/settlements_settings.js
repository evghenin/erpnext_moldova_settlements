const DEPOSIT_PATTERNS = {
	NovaPay: "PLATA PENTRU RAMBURS",
	MegaMega: "Conform contractul",
	"MAIB POS": "Transfer pentru operatiuni de acceptare a cardurilor",
	"MAIB Ecomm": "Transfer pentru operatiuni de acceptare a cardurilor la plata Ecomm",
};

frappe.ui.form.on("Settlements Settings", {
	setup(frm) {
		frm.set_query("bank_account", "sources", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {filters: {company: row.company}};
		});
	},
	refresh(frm) {
		for (const row of frm.doc.sources || []) {
			if (row.source && !row.deposit_description && DEPOSIT_PATTERNS[row.source]) {
				row.deposit_description = DEPOSIT_PATTERNS[row.source];
			}
		}
		frm.refresh_field("sources");
	},
});

frappe.ui.form.on("Settlements Source", {
	source(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.source === "MAIB POS") {
			row.create_payment_if_missing = 0;
		}
		if (DEPOSIT_PATTERNS[row.source]) {
			row.deposit_description = DEPOSIT_PATTERNS[row.source];
		}
		frm.refresh_field("sources");
	},
});
