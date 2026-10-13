"""Static web workspace route tests."""


def test_root_serves_the_workspace_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Woo PIM AI" in response.text
    assert 'id="panel-products"' in response.text
    assert 'id="panel-ai"' in response.text
    assert 'id="panel-sync"' in response.text


def test_static_ui_assets_are_served(client):
    stylesheet = client.get("/static/style.css")
    script = client.get("/static/app.js")
    assert stylesheet.status_code == 200
    assert "badge-success" in stylesheet.text
    assert script.status_code == 200
    assert 'fetch(' in script.text
