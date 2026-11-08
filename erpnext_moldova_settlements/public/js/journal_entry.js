frappe.ui.form.on("Journal Entry", {
	refresh(frm) {
		ignore_register_on_cancel(frm);
	},
});

function ignore_register_on_cancel(frm) {
	frm.ignore_doctypes_on_cancel_all = frm.ignore_doctypes_on_cancel_all || [];
	if (!frm.ignore_doctypes_on_cancel_all.includes("Settlement Register")) {
		frm.ignore_doctypes_on_cancel_all.push("Settlement Register");
	}
}
