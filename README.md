### QuickBooks Online and Time Integration

Integrating QuickBooks Online accounting data and QuickBooks Time webhook data with ERPNext.

### QuickBooks Online

This app adds a QuickBooks Online dashboard for ERPNext with:

- OAuth 2.0 setup for sandbox or production QuickBooks Online apps.
- Native ERPNext imports for accounting-core data including accounts, customers, vendors, items, invoices, bills, payments, journal entries, estimates, purchase orders, and deposits.
- Raw payload storage and sync mappings for auditability and idempotent updates.
- Resync preview before overwrite, with conflict detection for locally edited mapped fields.
- Webhook handling plus scheduled CDC polling for near-real-time updates and missed-event recovery.

Open the dashboard at `/app/quickbooks-online-dashboard` after installing and migrating the app.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app qb_time_integration
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/qb_time_integration
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
