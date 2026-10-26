import importlib, pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    import app as m
    importlib.reload(m)
    return m.app.test_client()


def test_airports(client):
    assert len(client.get("/api/airports").get_json()) == 5


def test_search(client):
    r = client.get("/api/flights?from=SVO&to=LED").get_json()
    assert r and all(f["to_code"] == "LED" for f in r)


def test_buy_and_validation(client):
    fid = client.get("/api/flights").get_json()[0]["id"]
    assert client.post("/api/tickets", json={"flight_id": fid}).status_code == 400
    r = client.post("/api/tickets", json={"flight_id": fid, "passenger": "Иван Иванов", "email": "a@b.ru"})
    assert r.status_code == 201
    assert client.get(f"/api/tickets/{r.get_json()['id']}").status_code == 200
