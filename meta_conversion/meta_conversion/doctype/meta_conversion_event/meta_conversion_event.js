frappe.ui.form.on("Meta Conversion Event", {
    refresh(frm) {
        if (!frm.is_new() && ["Skipped", "Tested", "Failed"].includes(frm.doc.status) && frappe.user.has_role("System Manager")) {
            frm.add_custom_button(__("Re-evaluate"), () => frappe.call({
                method: "meta_conversion.api.reevaluate",
                args: {event_name: frm.doc.name}, freeze: true,
                callback: () => frm.reload_doc()
            }));
        }
    }
});
