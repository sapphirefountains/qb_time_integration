import base64
import hashlib
import hmac
import sys
import types


def install_frappe_stub():
	frappe = types.ModuleType("frappe")
	frappe_utils = types.ModuleType("frappe.utils")
	frappe_utils.now_datetime = lambda: None
	frappe_utils.get_datetime = lambda value: value
	frappe_utils.add_to_date = lambda value=None, **kwargs: value
	frappe.utils = frappe_utils
	frappe.db = types.SimpleNamespace(
		exists=lambda doctype, name: name in {"All Customer Groups", "All Territories", "All Supplier Groups", "All Item Groups", "Nos"},
		get_value=lambda *args, **kwargs: None,
	)
	frappe.get_all = lambda doctype, filters=None, fields=None, limit_page_length=None, **kwargs: [
		types.SimpleNamespace(name="Acme Supply")
	] if doctype == "Customer" and filters == {"customer_name": "Acme Supply"} else []
	frappe.get_meta = lambda doctype: types.SimpleNamespace(has_field=lambda fieldname: False)
	sys.modules.setdefault("frappe", frappe)
	sys.modules.setdefault("frappe.utils", frappe_utils)
	return frappe


def test_ordered_entities_imports_masters_before_transactions():
	install_frappe_stub()
	from qb_time_integration.quickbooks_time_integration.quickbooks_online.sync import ordered_entities

	assert ordered_entities(["Invoice", "Customer", "Item", "Account"]) == ["Account", "Customer", "Item", "Invoice"]


def test_verify_intuit_signature_accepts_valid_hmac():
	install_frappe_stub()
	from qb_time_integration.quickbooks_time_integration.quickbooks_online.utils import verify_intuit_signature

	body = b'{"eventNotifications":[]}'
	token = "secret"
	signature = base64.b64encode(hmac.new(token.encode(), body, hashlib.sha256).digest()).decode()

	assert verify_intuit_signature(body, signature, token)
	assert not verify_intuit_signature(body, "bad", token)


def test_customer_mapping_uses_native_erpnext_fields():
	install_frappe_stub()
	from qb_time_integration.quickbooks_time_integration.quickbooks_online.mapping import map_qbo_to_erpnext

	doctype, values = map_qbo_to_erpnext(
		"Customer",
		{"Id": "1", "DisplayName": "Acme Supply", "CompanyName": "Acme Supply"},
		types.SimpleNamespace(company="Demo Company"),
	)

	assert doctype == "Customer"
	assert values["customer_name"] == "Acme Supply"
	assert values["customer_type"] == "Company"


def test_customer_auto_match_uses_existing_customer_name():
	install_frappe_stub()
	from qb_time_integration.quickbooks_time_integration.quickbooks_online.mapping import find_existing_match

	match = find_existing_match(
		"Customer",
		{"Id": "1", "DisplayName": "Acme Supply", "CompanyName": "Acme Supply"},
		types.SimpleNamespace(company="Demo Company"),
	)

	assert match["status"] == "matched"
	assert match["name"] == "Acme Supply"
	assert match["rule"] == "customer_name"
