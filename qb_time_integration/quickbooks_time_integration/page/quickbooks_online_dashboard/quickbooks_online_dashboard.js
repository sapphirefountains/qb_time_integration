frappe.pages["quickbooks-online-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("QuickBooks Online"),
		single_column: true,
	});

	page.set_primary_action(__("Import All"), () => runImportAll(), "download");
	page.add_action_item(__("Open Settings"), () => frappe.set_route("Form", "QuickBooks Online Settings"));
	page.add_action_item(__("Preview Resync"), () => previewResync());
	page.add_action_item(__("Retry Failed"), () => retryFailed());

	const root = $(`
		<div class="qbo-dashboard">
			<div class="qbo-status-grid">
				<div class="qbo-status-item">
					<div class="qbo-label">${__("Connection")}</div>
					<div class="qbo-value" data-field="status">-</div>
				</div>
				<div class="qbo-status-item">
					<div class="qbo-label">${__("Environment")}</div>
					<div class="qbo-value" data-field="environment">-</div>
				</div>
				<div class="qbo-status-item">
					<div class="qbo-label">${__("Realm ID")}</div>
					<div class="qbo-value" data-field="realm_id">-</div>
				</div>
				<div class="qbo-status-item">
					<div class="qbo-label">${__("Failed Logs")}</div>
					<div class="qbo-value" data-field="failed_records">0</div>
				</div>
			</div>
			<div class="qbo-toolbar">
				<button class="btn btn-default" data-action="connect">${__("Connect QuickBooks")}</button>
				<button class="btn btn-default" data-action="preview">${__("Preview Resync")}</button>
				<button class="btn btn-primary" data-action="import">${__("Import All")}</button>
			</div>
			<div class="qbo-section">
				<h4>${__("Accounting Core")}</h4>
				<div class="qbo-entity-list"></div>
			</div>
			<div class="qbo-section">
				<h4>${__("Recent Sync Logs")}</h4>
				<div class="qbo-log-list"></div>
			</div>
		</div>
	`).appendTo(page.body);

	root.on("click", "[data-action='connect']", () => connectQuickBooks());
	root.on("click", "[data-action='preview']", () => previewResync());
	root.on("click", "[data-action='import']", () => runImportAll());
	root.on("click", "[data-entity]", (event) => {
		const entity = $(event.currentTarget).attr("data-entity");
		const qboId = root.find(`[data-qbo-id='${entity}']`).val();
		if (!qboId) {
			frappe.msgprint(__("Enter a QuickBooks ID before syncing this entity."));
			return;
		}
		syncEntity(entity, qboId);
	});

	renderEntities(root);
	refresh(root);
};

const QBO_ENTITIES = [
	"Account",
	"Customer",
	"Vendor",
	"Item",
	"TaxCode",
	"Invoice",
	"Bill",
	"Payment",
	"JournalEntry",
	"Estimate",
	"PurchaseOrder",
	"Deposit",
];

function renderEntities(root) {
	const list = root.find(".qbo-entity-list");
	list.empty();
	QBO_ENTITIES.forEach((entity) => {
		$(`
			<div class="qbo-entity-row">
				<div class="qbo-entity-name">${entity}</div>
				<input class="form-control input-sm" data-qbo-id="${entity}" placeholder="${__("QuickBooks ID")}" />
				<button class="btn btn-xs btn-default" data-entity="${entity}">${__("Sync")}</button>
			</div>
		`).appendTo(list);
	});
}

function refresh(root) {
	frappe.call({
		method: "qb_time_integration.quickbooks_time_integration.quickbooks_online.api.get_dashboard_status",
		callback(response) {
			const data = response.message || {};
			const settings = data.settings || {};
			root.find("[data-field='status']").text(settings.status || "-");
			root.find("[data-field='environment']").text(settings.environment || "-");
			root.find("[data-field='realm_id']").text(settings.realm_id || "-");
			root.find("[data-field='failed_records']").text(data.failed_records || 0);
			renderLogs(root, data.latest_logs || []);
		},
	});
}

function renderLogs(root, logs) {
	const list = root.find(".qbo-log-list");
	list.empty();
	if (!logs.length) {
		list.html(`<div class="text-muted">${__("No sync logs yet.")}</div>`);
		return;
	}
	logs.forEach((log) => {
		$(`
			<div class="qbo-log-row">
				<div>
					<a data-route="Form/QuickBooks Sync Log/${log.name}">${log.name}</a>
					<div class="text-muted">${log.sync_type || ""} ${log.entity_type || ""}</div>
				</div>
				<div>${log.status}</div>
				<div>${__("C")} ${log.created_count || 0} / ${__("U")} ${log.updated_count || 0} / ${__("X")} ${log.conflict_count || 0}</div>
			</div>
		`).appendTo(list);
	});
}

function connectQuickBooks() {
	frappe.db.get_single_value("QuickBooks Online Settings", "environment").then((environment) => {
		frappe.call({
			method: "qb_time_integration.quickbooks_time_integration.quickbooks_online.api.start_oauth",
			args: { environment },
			callback(response) {
				const url = response.message && response.message.authorization_url;
				if (url) {
					window.location.href = url;
				}
			},
		});
	});
}

function runImportAll() {
	frappe.confirm(__("Import accounting-core QuickBooks Online data now?"), () => {
		frappe.call({
			method: "qb_time_integration.quickbooks_time_integration.quickbooks_online.api.import_all",
			freeze: true,
			freeze_message: __("Importing QuickBooks Online data..."),
			callback(response) {
				frappe.msgprint(__("Import started/completed in log {0}", [response.message]));
				frappe.pages["quickbooks-online-dashboard"].page.wrapper && location.reload();
			},
		});
	});
}

function previewResync() {
	frappe.call({
		method: "qb_time_integration.quickbooks_time_integration.quickbooks_online.api.preview_resync",
		freeze: true,
		freeze_message: __("Building resync preview..."),
		callback(response) {
			const result = response.message || {};
			const summary = result.summary || {};
			const message = __(
				"Preview {0}: {1} creates, {2} updates, {3} deletes, {4} conflicts.",
				[
					result.preview_id,
					summary.created || 0,
					summary.updated || 0,
					summary.deleted || 0,
					summary.conflicts || 0,
				],
			);
			frappe.confirm(message + "<br>" + __("Run overwrite resync for QuickBooks-owned fields?"), () => {
				frappe.call({
					method: "qb_time_integration.quickbooks_time_integration.quickbooks_online.api.run_resync",
					args: { preview_id: result.preview_id },
					freeze: true,
					freeze_message: __("Running resync..."),
					callback(runResponse) {
						frappe.msgprint(__("Resync completed in log {0}", [runResponse.message.sync_log]));
					},
				});
			});
		},
	});
}

function retryFailed() {
	frappe.call({
		method: "qb_time_integration.quickbooks_time_integration.quickbooks_online.api.retry_failed",
		freeze: true,
		freeze_message: __("Retrying failed syncs..."),
		callback() {
			frappe.msgprint(__("Retry requested."));
		},
	});
}

function syncEntity(entity, qboId) {
	frappe.call({
		method: "qb_time_integration.quickbooks_time_integration.quickbooks_online.api.sync_entity",
		args: { entity_type: entity, qbo_id: qboId },
		freeze: true,
		freeze_message: __("Syncing {0}...", [entity]),
		callback(response) {
			frappe.msgprint(__("{0} synced in log {1}", [entity, response.message.sync_log]));
		},
	});
}

