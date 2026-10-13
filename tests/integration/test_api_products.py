"""Product and attribute API integration tests."""


def product_payload(sku="MOUSE-1", **overrides):
    payload = {"sku": sku, "title": "Wireless Mouse", "description": "A mouse", "price": 19.5, "tags": ["wireless"], "category": "Electronics", "attributes": {}, "status": "draft"}
    payload.update(overrides)
    return payload


def test_product_crud_filter_and_pagination(client):
    first = client.post("/products", json=product_payload()).json()
    client.post("/products", json=product_payload("MOUSE-2", status="published", category="Office"))
    assert first["id"] == 1
    assert client.get("/products", params={"status": "draft", "category": "Electronics", "limit": 1}).json()[0]["sku"] == "MOUSE-1"
    assert client.get(f"/products/{first['id']}").status_code == 200
    assert client.patch(f"/products/{first['id']}", json={"title": "Updated"}).json()["title"] == "Updated"
    assert client.delete(f"/products/{first['id']}").status_code == 204
    assert client.get(f"/products/{first['id']}").json()["error"]["code"] == "not_found"


def test_duplicate_sku_and_missing_product_error_envelopes(client):
    client.post("/products", json=product_payload())
    duplicate = client.post("/products", json=product_payload())
    missing = client.get("/products/99")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"
    assert missing.status_code == 404
    assert set(missing.json()["error"]) == {"code", "message", "details"}


def test_attribute_crud_and_product_attribute_validation(client):
    definition = client.post("/attributes", json={"name": "color", "type": "enum", "required": True, "allowed_values": ["black", "white"], "category_scope": "Mice"})
    assert definition.status_code == 201
    invalid = client.post("/products", json=product_payload(category="Mice"))
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "attribute_validation_error"
    valid = client.post("/products", json=product_payload(category="Mice", attributes={"color": "black"}))
    assert valid.status_code == 201
    assert client.get("/attributes").json()[0]["name"] == "color"
    assert client.get(f"/attributes/{definition.json()['id']}").status_code == 200
    assert client.delete(f"/attributes/{definition.json()['id']}").status_code == 204


def test_unknown_attribute_rejected_and_enum_definition_requires_values(client):
    bad_definition = client.post("/attributes", json={"name": "shade", "type": "enum"})
    assert bad_definition.status_code == 422
    bad_product = client.post("/products", json=product_payload(attributes={"unknown": "x"}))
    assert bad_product.status_code == 422
