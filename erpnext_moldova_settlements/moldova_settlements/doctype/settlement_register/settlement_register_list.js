frappe.listview_settings["Settlement Register"] = {
	get_indicator(doc) {
		const colors = {Draft: "gray", Unreconciled: "orange", Reconciled: "green"};
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
