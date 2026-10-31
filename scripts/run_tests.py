"""Tạo CSDL kiểm thử riêng, chạy pytest và chỉ xóa CSDL do chính lần chạy này tạo."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import psycopg
from psycopg import sql

from qlcv.config import ROOT, settings
from qlcv.schema_check import contract


def fingerprint(pg):
    result = {}
    with psycopg.connect(**pg) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        for name in ("departments", "users", "projects", "project_members", "tasks", "task_members", "attachments", "audit_logs"):
            result[name] = conn.execute(sql.SQL("SELECT count(*),md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' ORDER BY to_jsonb(t)::text),'')) FROM qlcv.{} t").format(sql.Identifier(name))).fetchone()
    return result


def prepare_preview(pg):
    import bcrypt
    with psycopg.connect(**pg, autocommit=True) as conn:
        conn.execute("DROP SCHEMA qlcv CASCADE")
        conn.execute((ROOT / "database" / "init.sql").read_text(encoding="utf-8"))
        with conn.transaction():
            admin_id = conn.execute("SELECT id FROM qlcv.users WHERE username='admin'").fetchone()[0]
            conn.execute("SELECT qlcv.set_actor(%s)", (admin_id,))
            conn.execute("UPDATE qlcv.users SET password_hash=%s", (bcrypt.hashpw(b"KiemThu2026!", bcrypt.gensalt(rounds=4)).decode(),))
    from qlcv import create_app
    app = create_app({"TESTING": False, "PG_CONFIG": pg, "SECRET_KEY": uuid4().hex,
                      "UPLOAD_FOLDER": str(ROOT / ".tmp" / "preview-uploads")})
    client = app.test_client()
    with psycopg.connect(**pg) as conn:
        employee_id = conn.execute("SELECT id FROM qlcv.users WHERE username='phanmem_nv01'").fetchone()[0]
    # Chỉ tắt CSRF trong bước chuẩn bị dữ liệu của bản xem thử; bật lại trước khi phục vụ.
    app.config["WTF_CSRF_ENABLED"] = False
    client.post("/dang-nhap", data={"username": "tbp_phanmem", "password": "KiemThu2026!"})
    for title, description, percentage in [
        ("Nâng cấp hệ thống quản lý", "Chuẩn hóa quy trình và nâng cấp hệ thống phục vụ công việc nội bộ.", 65),
        ("Triển khai hạ tầng văn phòng", "Phối hợp triển khai thiết bị và kết nối cho các bộ phận.", 100),
        ("Số hóa tài liệu nghiệp vụ", "Tập hợp và số hóa các tài liệu dùng chung của công ty.", 0),
    ]:
        response = client.post("/du-an/tao", data={"name": title, "description": description})
        project_id = int(response.location.rsplit("/", 1)[-1])
        client.post(f"/thanh-vien/project/{project_id}", data={"user_id": employee_id})
        response = client.post("/cong-viec/tao", data={"project_id": project_id, "assignee_id": employee_id, "name": "Khảo sát và thực hiện " + title.lower(), "description": "Ghi nhận yêu cầu, thực hiện công việc và cập nhật kết quả."})
        task_id = int(response.location.rsplit("/", 1)[-1])
        client.post(f"/cong-viec/{task_id}/tien-do", data={"progress": percentage})
    app.config["WTF_CSRF_ENABLED"] = True
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve-preview", action="store_true", help="Sau kiểm thử, chạy bản xem thử bằng dữ liệu kiểm thử ở cổng 5001.")
    args = parser.parse_args()
    pg = settings()["PG_CONFIG"]
    before = fingerprint(pg)
    with psycopg.connect(**pg) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        production_contract = contract(conn)
    name = "qlcv_test_" + uuid4().hex
    test_pg = {**pg, "dbname": name}
    created = False
    result = 1
    try:
        with psycopg.connect(**pg, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'").format(sql.Identifier(name)))
            created = True
        print("Đã tạo CSDL kiểm thử riêng:", name, flush=True)
        with psycopg.connect(**test_pg, autocommit=True) as conn:
            conn.execute((ROOT / "database" / "init.sql").read_text(encoding="utf-8"))
            same_schema = contract(conn) == production_contract
        print("Schema đang dùng khớp SQL đầu vào:", "đúng" if same_schema else "KHÁC BIỆT", flush=True)
        if not same_schema:
            print("Dừng kiểm thử: cần đối chiếu schema trước khi kết luận.", flush=True)
            return 1
        output = ROOT / "test-results"
        output.mkdir(exist_ok=True)
        env = {**os.environ, "QLCV_TEST_DATABASE": name, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.call([sys.executable, "-m", "pytest", "-q", "tests", "--basetemp=.tmp/pytest", "--junitxml=test-results/pytest.xml"], cwd=ROOT, env=env)
        unchanged = fingerprint(pg) == before
        (output / "verification.json").write_text(json.dumps({"pytest_exit_code": result, "production_unchanged": unchanged, "schema_matches_input_sql": same_schema}, indent=2), encoding="utf-8")
        print("Dữ liệu đang dùng không thay đổi:", "đúng" if unchanged else "CẦN KIỂM TRA", flush=True)
        if not unchanged:
            result = 1
        if args.serve_preview and result == 0:
            from waitress import serve
            app = prepare_preview(test_pg)
            print("Bản xem thử trên CSDL riêng: http://127.0.0.1:5001", flush=True)
            serve(app, host="127.0.0.1", port=5001)
    except psycopg.Error as exc:
        print("Không tạo/chạy được CSDL kiểm thử riêng. Kiểm tra quyền CREATEDB và kết nối. Mã:", exc.sqlstate or "kết nối", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        if created:
            # Tên ngẫu nhiên chỉ do lần chạy này tạo, không bao giờ lấy từ .env để DROP.
            with psycopg.connect(**pg, autocommit=True) as conn:
                conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            print("Đã dọn cơ sở dữ liệu kiểm thử riêng.", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
