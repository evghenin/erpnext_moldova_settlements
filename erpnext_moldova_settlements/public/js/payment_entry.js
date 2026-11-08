frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		frm.ignore_doctypes_on_cancel_all = frm.ignore_doctypes_on_cancel_all || [];
		if (!frm.ignore_doctypes_on_cancel_all.includes("Settlement Register")) {
			frm.ignore_doctypes_on_cancel_all.push("Settlement Register");
		}
	},
});
