import os
from pathlib import Path

import bcrypt
import psycopg
import pytest

from qlcv import create_app
from qlcv.config import ROOT, settings

PASSWORD = "KiemThu2026!"


@pytest.fixture
def env(tmp_path):
    pg = settings()["PG_CONFIG"]
    name = os.environ.get("QLCV_TEST_DATABASE", "")
    if not name.startswith("qlcv_test_") or len(name) != 42 or name == pg["dbname"]:
        pytest.fail("Chạy scripts/run_tests.py để tạo CSDL kiểm thử riêng; không kiểm thử ghi trên .env.")
    test_pg = {**pg, "dbname": name}
    with psycopg.connect(**test_pg, autocommit=True) as conn:
        conn.execute("DROP SCHEMA qlcv CASCADE")
        conn.execute((ROOT / "database" / "init.sql").read_text(encoding="utf-8"))
        with conn.transaction():
            admin_id = conn.execute("SELECT id FROM qlcv.users WHERE username='admin'").fetchone()[0]
            conn.execute("SELECT qlcv.set_actor(%s)", (admin_id,))
            conn.execute("UPDATE qlcv.users SET password_hash=%s", (bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode(),))
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SECRET_KEY": "khoa-chi-dung-cho-kiem-thu",
                      "PG_CONFIG": test_pg, "UPLOAD_FOLDER": str(tmp_path / "uploads")})
    def query(sql, params=()):
        with psycopg.connect(**test_pg) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            return conn.execute(sql, params).fetchall()
    def login(name="admin"):
        client = app.test_client()
        response = client.post("/dang-nhap", data={"username": name, "password": PASSWORD})
        assert response.status_code == 302
        return client
    class Env:
        pass
    env = Env()
    env.app, env.query, env.login, env.pg = app, query, login, test_pg
    env.ids = dict(query("SELECT username,id FROM qlcv.users"))
    yield env
    app.extensions["engine"].dispose()


@pytest.fixture
def work(env):
    client = env.login("tbp_phanmem")
    response = client.post("/du-an/tao", data={"name": "Dự án A", "description": "NỘI DUNG DỰ ÁN BÍ MẬT"})
    assert response.status_code == 302
    p = int(response.location.rsplit("/", 1)[-1])
    for uid in (env.ids['phanmem_nv01'], env.ids['phanmem_nv02']):
        assert client.post(f"/thanh-vien/project/{p}", data={"user_id": uid}).status_code == 302
    response = client.post("/cong-viec/tao", data={"project_id": p, "assignee_id": env.ids['phanmem_nv01'], "name": "Công việc A", "description": "NỘI DUNG CÔNG VIỆC BÍ MẬT"})
    assert response.status_code == 302
    t = int(response.location.rsplit("/", 1)[-1])
    return p, t
