"""
Tests for the API documentation pages.
"""


def test_docs_serves_swagger_ui(client):
    response = client.get("/docs/")

    assert response.status_code == 200
    assert b"swagger-ui" in response.data


def test_docs_without_trailing_slash_redirects_to_swagger(client):
    response = client.get("/docs", follow_redirects=True)

    assert response.status_code == 200
    assert b"swagger-ui" in response.data


def test_openapi_spec_is_served(client):
    response = client.get("/docs/openapi.json")

    assert response.status_code == 200
    assert response.json["info"]["title"] == "Shop Payments API"
