def test_api_root_identifies_inventory(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"mensaje": "API de Inventario de Repuestos Activa"}
