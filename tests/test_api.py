def test_register_and_login(client):
    response = client.post("/register", json={"username": "testuser", "password": "pass"})
    assert response.status_code == 200
    assert "access_token" in response.json()

    response_dup = client.post("/register", json={"username": "testuser", "password": "123"})
    assert response_dup.status_code == 400

    response_login = client.post("/token", data={"username": "testuser", "password": "pass"})
    assert response_login.status_code == 200

def test_shorten_url(client):
    response = client.post("/links/shorten", json={"original_url": "https://fastapi.tiangolo.com/"})
    assert response.status_code == 200
    assert "short_code" in response.json()

def test_shorten_url_invalid_data(client):
    response = client.post("/links/shorten", json={"wrong_field": "data"})
    assert response.status_code == 422

def test_redirect_and_stats(client):
    client.post("/links/shorten", json={"original_url": "https://google.com", "custom_alias": "goog"})

    redirect_res = client.get("/goog", follow_redirects=False)
    assert redirect_res.status_code in [307, 302, 301]
    assert redirect_res.headers["location"] == "https://google.com"

    stats_res = client.get("/links/goog/stats")
    assert stats_res.status_code == 200
    assert stats_res.json()["clicks"] == 1

def test_delete_link(client):
    client.post("/register", json={"username": "del_user", "password": "123"})
    token = client.post("/token", data={"username": "del_user", "password": "123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/links/shorten", json={"original_url": "https://test.com", "custom_alias": "todel"}, headers=headers)

    del_res = client.delete("/links/todel", headers=headers)
    assert del_res.status_code == 200

    assert client.get("/links/todel/stats").status_code == 404
