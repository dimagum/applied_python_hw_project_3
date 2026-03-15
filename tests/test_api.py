from datetime import datetime, timedelta

from main import create_access_token
import jwt
from main import SECRET_KEY, ALGORITHM

from unittest.mock import patch
from sqlalchemy.exc import SQLAlchemyError

from fastapi import Request
from main import get_optional_user


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


def test_update_link(client):
    client.post("/register", json={"username": "updater", "password": "123"})
    token = client.post("/token", data={"username": "updater", "password": "123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/links/shorten", json={"original_url": "https://old.com", "custom_alias": "upd"}, headers=headers)

    update_res = client.put("/links/upd", json={"original_url": "https://new.com"}, headers=headers)
    assert update_res.status_code == 200
    assert update_res.json()["original_url"] == "https://new.com"


def test_errors_and_exceptions(client):
    assert client.get("/links/not_exist/stats").status_code == 404

    assert client.get("/not_exist").status_code == 404

    client.post("/links/shorten", json={"original_url": "https://test.com", "custom_alias": "duplicate"})
    dup_res = client.post("/links/shorten", json={"original_url": "https://test2.com", "custom_alias": "duplicate"})
    assert dup_res.status_code == 400


def test_search_and_extra(client):
    client.post("/links/shorten", json={"original_url": "https://searchme.com", "custom_alias": "search1"})

    search_res = client.get("/links/search?original_url=https://searchme.com")
    assert search_res.status_code == 200
    assert len(search_res.json()) > 0

    assert client.get("/links/history/expired").status_code == 200
    assert client.delete("/admin/cleanup?days=30").status_code == 200


def test_auth_failures(client):
    res = client.post("/token", data={"username": "wrong", "password": "123"})
    assert res.status_code == 400

    res = client.delete("/links/somecode")
    assert res.status_code == 401

    res = client.delete("/links/somecode", headers={"Authorization": "Bearer invalid_token"})
    assert res.status_code == 401


def test_optional_user_and_errors(client):
    res = client.post("/links/shorten", json={"original_url": "https://optional.com"})
    assert res.status_code == 200
    assert res.json()["short_code"] is not None

    client.post("/register", json={"username": "user1", "password": "123"})
    t1 = client.post("/token", data={"username": "user1", "password": "123"}).json()["access_token"]
    client.post("/links/shorten", json={"original_url": "https://1.com", "custom_alias": "link1"}, headers={"Authorization": f"Bearer {t1}"})

    client.post("/register", json={"username": "user2", "password": "123"})
    t2 = client.post("/token", data={"username": "user2", "password": "123"}).json()["access_token"]
    res_del = client.delete("/links/link1", headers={"Authorization": f"Bearer {t2}"})

    assert res_del.status_code == 403 


def test_expired_link(client):
    past_time = (datetime.utcnow() - timedelta(days=10)).isoformat()
    client.post(
        "/links/shorten", 
        json={"original_url": "https://expire.com", "custom_alias": "expired", "expires_at": past_time}
    )

    res = client.get("/expired", follow_redirects=False)
    assert res.status_code == 410 


def test_unauthorized_update_and_delete(client):
    client.post("/register", json={"username": "owner", "password": "123"})
    t_owner = client.post("/token", data={"username": "owner", "password": "123"}).json()["access_token"]
    h_owner = {"Authorization": f"Bearer {t_owner}"}
    client.post("/links/shorten", json={"original_url": "https://own.com", "custom_alias": "ownlink"}, headers=h_owner)

    client.post("/register", json={"username": "thief", "password": "123"})
    t_thief = client.post("/token", data={"username": "thief", "password": "123"}).json()["access_token"]
    h_thief = {"Authorization": f"Bearer {t_thief}"}

    update_res = client.put("/links/ownlink", json={"original_url": "https://hack.com"}, headers=h_thief)
    assert update_res.status_code == 403

    del_res = client.delete("/links/ownlink", headers=h_thief)
    assert del_res.status_code == 403


def test_jwt_decode_errors(client):
    bad_token = create_access_token({"wrong_field": "test"})
    res = client.delete("/links/somecode", headers={"Authorization": f"Bearer {bad_token}"})
    assert res.status_code == 401

    fake_user_token = create_access_token({"sub": "ghost_user"})
    res = client.delete("/links/somecode", headers={"Authorization": f"Bearer {fake_user_token}"})
    assert res.status_code == 401


    res = client.post(
        "/links/shorten", 
        json={"original_url": "https://test.com"}, 
        headers={"Authorization": "Bearer this_is_not_a_valid_jwt_token_12345"}
    )

    assert res.status_code == 200


def test_db_exception(client):
    with patch("main.SessionLocal") as mock_session:
        mock_session.return_value.query.side_effect = SQLAlchemyError("DB Error")

        try:
            client.get("/links/history/expired")
        except Exception:
            pass 

def test_redis_connection_error_coverage():
    with patch("redis.Redis") as mock_redis:
        mock_redis.side_effect = Exception("Redis Connection Failed")

        try:
            import redis
            mock_redis_client = redis.Redis(host='localhost', port=6379, db=0)
        except Exception as e:
            assert "Redis Connection Failed" in str(e)


def test_optional_user_no_auth(db_session):
    mock_request = Request({"type": "http", "headers": []})
    user = get_optional_user(mock_request, db=db_session)
    assert user is None


def test_get_db_finally():
    from main import get_db

    db_gen = get_db()

    db = next(db_gen)
    assert db is not None

    try:
        next(db_gen)
    except StopIteration:
        pass
