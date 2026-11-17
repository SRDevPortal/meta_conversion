frappe.ui.form.on("Meta Conversion Settings", {
    setup(frm) {
        frm.set_query("channel_account", () => ({
            filters: {channel_type: "Interakt", is_active: 1}
        }));
    }
});
