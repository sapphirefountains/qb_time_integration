from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from qb_time_integration.quickbooks_time_integration.quickbooks_online.constants import ENTITY_DOCTYPE_MAP
from qb_time_integration.quickbooks_time_integration.quickbooks_online.utils import (
	json_dumps,
	json_loads,
	parse_qbo_datetime,
)


def get_erpnext_doctype(entity_type: str) -> str | None:
	return ENTITY_DOCTYPE_MAP.get(entity_type)


def map_qbo_to_erpnext(entity_type: str, payload: dict, settings) -> tuple[str | None, dict]:
	mappers = {
		"Account": _map_account,
		"Customer": _map_customer,
		"Vendor": _map_supplier,
		"Item": _map_item,
		"Invoice": _map_sales_invoice,
		"Bill": _map_purchase_invoice,
		"Payment": _map_payment_entry,
		"JournalEntry": _map_journal_entry,
		"Estimate": _map_quotation,
		"PurchaseOrder": _map_purchase_order,
		"Deposit": _map_payment_entry,
		"TaxCode": _map_tax_code,
	}
	mapper = mappers.get(entity_type)
	if not mapper:
		return None, {}
	return mapper(payload, settings)


def upsert_entity(entity_type: str, payload: dict, settings, *, overwrite=False, preview=False):
	erpnext_doctype, values = map_qbo_to_erpnext(entity_type, payload, settings)
	if not erpnext_doctype:
		return {"action": "skipped", "reason": "No native ERPNext mapping"}

	qbo_id = str(payload.get("Id"))
	if not qbo_id:
		return {"action": "skipped", "reason": "QBO payload has no Id"}

	mapping = get_mapping(entity_type, qbo_id)
	if mapping and mapping.erpnext_name and frappe.db.exists(erpnext_doctype, mapping.erpnext_name):
		doc = frappe.get_doc(erpnext_doctype, mapping.erpnext_name)
		conflicts = detect_conflicts(doc, values, mapping)
		if conflicts and not overwrite:
			if not preview:
				mapping.conflict_status = "Conflict"
				mapping.save(ignore_permissions=True)
			return {"action": "conflict", "doctype": erpnext_doctype, "name": doc.name, "fields": conflicts}
		if preview:
			return {"action": "update", "doctype": erpnext_doctype, "name": doc.name, "fields": list(values)}
		apply_values(doc, values)
		doc.save(ignore_permissions=True)
		save_mapping(entity_type, qbo_id, payload, erpnext_doctype, doc.name, values, conflict_status="Clean")
		return {"action": "updated", "doctype": erpnext_doctype, "name": doc.name}

	if preview:
		return {"action": "create", "doctype": erpnext_doctype, "fields": list(values)}

	doc = frappe.new_doc(erpnext_doctype)
	apply_values(doc, values)
	doc.insert(ignore_permissions=True)
	save_mapping(entity_type, qbo_id, payload, erpnext_doctype, doc.name, values, conflict_status="Clean")
	return {"action": "created", "doctype": erpnext_doctype, "name": doc.name}


def mark_deleted(entity_type: str, qbo_id: str, *, preview=False):
	mapping = get_mapping(entity_type, qbo_id)
	if preview:
		return {"action": "delete", "mapping": mapping.name if mapping else None}
	if mapping:
		mapping.deleted = 1
		mapping.conflict_status = "Clean"
		mapping.save(ignore_permissions=True)
	return {"action": "deleted"}


def get_mapping(entity_type: str, qbo_id: str):
	name = frappe.db.get_value(
		"QuickBooks Sync Mapping",
		{"qbo_entity_type": entity_type, "qbo_id": str(qbo_id)},
		"name",
	)
	return frappe.get_doc("QuickBooks Sync Mapping", name) if name else None


def save_mapping(entity_type: str, qbo_id: str, payload: dict, erpnext_doctype: str, erpnext_name: str, values: dict, **extra):
	mapping = get_mapping(entity_type, qbo_id) or frappe.new_doc("QuickBooks Sync Mapping")
	mapping.qbo_entity_type = entity_type
	mapping.qbo_id = str(qbo_id)
	mapping.erpnext_doctype = erpnext_doctype
	mapping.erpnext_name = erpnext_name
	mapping.sync_token = payload.get("SyncToken")
	mapping.last_qbo_updated_at = parse_qbo_datetime((payload.get("MetaData") or {}).get("LastUpdatedTime"))
	mapping.last_synced_at = now_datetime()
	mapping.deleted = 0
	mapping.owned_fields = json_dumps(values)
	for fieldname, value in extra.items():
		setattr(mapping, fieldname, value)
	if mapping.is_new():
		mapping.insert(ignore_permissions=True)
	else:
		mapping.save(ignore_permissions=True)
	return mapping


def detect_conflicts(doc, incoming_values: dict, mapping) -> list[str]:
	owned = json_loads(mapping.owned_fields, default={}) or {}
	conflicts = []
	for fieldname, previous_value in owned.items():
		if fieldname not in incoming_values:
			continue
		current_value = doc.get(fieldname)
		if _normalize(current_value) != _normalize(previous_value) and _normalize(current_value) != _normalize(
			incoming_values[fieldname]
		):
			conflicts.append(fieldname)
	return conflicts


def apply_values(doc, values: dict):
	for fieldname, value in values.items():
		if value is not None:
			doc.set(fieldname, value)


def _normalize(value):
	return "" if value is None else str(value)


def _display_name(payload):
	return payload.get("DisplayName") or payload.get("FullyQualifiedName") or payload.get("Name") or payload.get("Id")


def _map_account(payload, settings):
	return "Account", {
		"account_name": payload.get("Name"),
		"company": settings.company,
		"is_group": 0,
		"account_type": _account_type(payload.get("AccountType")),
	}


def _map_customer(payload, settings):
	return "Customer", {
		"customer_name": _display_name(payload),
		"customer_type": "Company" if payload.get("CompanyName") else "Individual",
		"customer_group": _default_or_none("Customer Group", "All Customer Groups"),
		"territory": _default_or_none("Territory", "All Territories"),
	}


def _map_supplier(payload, settings):
	return "Supplier", {
		"supplier_name": _display_name(payload),
		"supplier_type": "Company" if payload.get("CompanyName") else "Individual",
		"supplier_group": _default_or_none("Supplier Group", "All Supplier Groups"),
	}


def _map_item(payload, settings):
	return "Item", {
		"item_code": payload.get("Sku") or payload.get("Name") or payload.get("Id"),
		"item_name": payload.get("Name"),
		"description": payload.get("Description"),
		"item_group": _default_or_none("Item Group", "All Item Groups"),
		"stock_uom": _default_or_none("UOM", "Nos"),
		"is_stock_item": 0,
	}


def _map_sales_invoice(payload, settings):
	return "Sales Invoice", {
		"company": settings.company,
		"customer": _linked_name("Customer", "Customer", payload.get("CustomerRef", {}).get("value")),
		"posting_date": payload.get("TxnDate"),
		"set_posting_time": 1,
		"items": _sales_items(payload),
		"remarks": f"Imported from QuickBooks Online Invoice {payload.get('DocNumber') or payload.get('Id')}",
	}


def _map_purchase_invoice(payload, settings):
	return "Purchase Invoice", {
		"company": settings.company,
		"supplier": _linked_name("Vendor", "Supplier", payload.get("VendorRef", {}).get("value")),
		"posting_date": payload.get("TxnDate"),
		"set_posting_time": 1,
		"items": _purchase_items(payload),
		"remarks": f"Imported from QuickBooks Online Bill {payload.get('DocNumber') or payload.get('Id')}",
	}


def _map_payment_entry(payload, settings):
	return "Payment Entry", {
		"company": settings.company,
		"posting_date": payload.get("TxnDate"),
		"payment_type": "Receive",
		"remarks": f"Imported from QuickBooks Online payment/deposit {payload.get('Id')}",
	}


def _map_journal_entry(payload, settings):
	return "Journal Entry", {
		"company": settings.company,
		"posting_date": payload.get("TxnDate"),
		"accounts": _journal_accounts(payload),
		"remark": f"Imported from QuickBooks Online Journal Entry {payload.get('DocNumber') or payload.get('Id')}",
	}


def _map_quotation(payload, settings):
	return "Quotation", {
		"company": settings.company,
		"quotation_to": "Customer",
		"party_name": _linked_name("Customer", "Customer", payload.get("CustomerRef", {}).get("value")),
		"transaction_date": payload.get("TxnDate"),
		"items": _sales_items(payload),
	}


def _map_purchase_order(payload, settings):
	return "Purchase Order", {
		"company": settings.company,
		"supplier": _linked_name("Vendor", "Supplier", payload.get("VendorRef", {}).get("value")),
		"transaction_date": payload.get("TxnDate"),
		"items": _purchase_items(payload),
	}


def _map_tax_code(payload, settings):
	return "Account", {
		"account_name": payload.get("Name") or f"QBO TaxCode {payload.get('Id')}",
		"company": settings.company,
		"is_group": 0,
		"account_type": "Tax",
	}


def _linked_name(qbo_entity_type: str, erpnext_doctype: str, qbo_id: str | None):
	if not qbo_id:
		return None
	return frappe.db.get_value(
		"QuickBooks Sync Mapping",
		{"qbo_entity_type": qbo_entity_type, "qbo_id": str(qbo_id), "erpnext_doctype": erpnext_doctype},
		"erpnext_name",
	)


def _default_or_none(doctype: str, name: str):
	return name if frappe.db.exists(doctype, name) else None


def _account_type(qbo_account_type):
	account_type_map = {
		"Bank": "Bank",
		"Accounts Receivable": "Receivable",
		"Accounts Payable": "Payable",
		"Credit Card": "Bank",
		"Fixed Asset": "Fixed Asset",
		"Expense": "Expense Account",
		"Other Expense": "Expense Account",
		"Income": "Income Account",
		"Other Income": "Income Account",
	}
	return account_type_map.get(qbo_account_type)


def _sales_items(payload):
	items = []
	for line in payload.get("Line", []) or []:
		detail = line.get("SalesItemLineDetail") or {}
		item_ref = detail.get("ItemRef") or {}
		item_code = _linked_name("Item", "Item", item_ref.get("value"))
		if not item_code:
			continue
		items.append(
			{
				"item_code": item_code,
				"description": line.get("Description") or item_ref.get("name"),
				"qty": detail.get("Qty") or 1,
				"rate": detail.get("UnitPrice") or line.get("Amount") or 0,
				"amount": line.get("Amount") or 0,
			}
		)
	return items


def _purchase_items(payload):
	items = []
	for line in payload.get("Line", []) or []:
		detail = line.get("ItemBasedExpenseLineDetail") or {}
		item_ref = detail.get("ItemRef") or {}
		item_code = _linked_name("Item", "Item", item_ref.get("value"))
		if not item_code:
			continue
		items.append(
			{
				"item_code": item_code,
				"description": line.get("Description") or item_ref.get("name"),
				"qty": detail.get("Qty") or 1,
				"rate": detail.get("UnitPrice") or line.get("Amount") or 0,
				"amount": line.get("Amount") or 0,
			}
		)
	return items


def _journal_accounts(payload):
	accounts = []
	for line in payload.get("Line", []) or []:
		detail = line.get("JournalEntryLineDetail") or {}
		account_ref = detail.get("AccountRef") or {}
		account = _linked_name("Account", "Account", account_ref.get("value"))
		if not account:
			continue
		amount = line.get("Amount") or 0
		posting_type = detail.get("PostingType")
		accounts.append(
			{
				"account": account,
				"debit_in_account_currency": amount if posting_type == "Debit" else 0,
				"credit_in_account_currency": amount if posting_type == "Credit" else 0,
			}
		)
	return accounts
