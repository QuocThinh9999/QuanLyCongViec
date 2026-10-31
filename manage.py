"""Công cụ vận hành; không thay thế schema SQL bằng mô hình tự sinh."""
import argparse
import sys
from pathlib import Path

import psycopg

from qlcv.config import ROOT, settings


def inspect_db(conn):
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        schema = conn.execute("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='qlcv')").fetchone()[0]
        objects = conn.execute("""SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'
            AND n.nspname NOT LIKE 'pg_temp%' AND c.relkind IN ('r','p','v','m','S','f')""").fetchall()
        extra_schemas = conn.execute("""SELECT nspname FROM pg_namespace WHERE nspname NOT IN ('public','pg_catalog','information_schema')
            AND nspname NOT LIKE 'pg_toast%' AND nspname NOT LIKE 'pg_temp%'""").fetchall()
        public_objects = conn.execute("""SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
            UNION ALL SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public' LIMIT 1""").fetchone()
        extensions = conn.execute("SELECT extname FROM pg_extension WHERE extname <> 'plpgsql'").fetchall()
        empty = not (objects or extra_schemas or public_objects or extensions)
        print("Kết nối PostgreSQL: thành công.")
        print("Schema qlcv: " + ("đã tồn tại; sử dụng trực tiếp." if schema else "chưa tồn tại."))
        if schema:
            for name in ("departments", "users", "projects", "tasks", "attachments", "audit_logs"):
                from psycopg import sql
                total = conn.execute(sql.SQL("SELECT count(*) FROM qlcv.{}").format(sql.Identifier(name))).fetchone()[0]
                print(f"{name}: {total} bản ghi")
            print("Vai trò:", conn.execute("SELECT role::text,count(*) FROM qlcv.users GROUP BY role ORDER BY role").fetchall())
        else:
            print("Cơ sở dữ liệu rỗng: " + ("có" if empty else "không; không được import."))
        return schema, empty


def main():
    parser = argparse.ArgumentParser(description="Kiểm tra, khởi tạo an toàn và dọn tệp Quản lý công việc.")
    parser.add_argument("command", choices=("check-db", "init-db", "clean-files"))
    parser.add_argument("--apply", action="store_true", help="Thực sự xóa tệp mồ côi trên 24 giờ; mặc định chỉ liệt kê.")
    args = parser.parse_args()
    config = settings()
    try:
        with psycopg.connect(**config["PG_CONFIG"], autocommit=True) as conn:
            schema, empty = inspect_db(conn)
            if args.command == "init-db":
                if schema:
                    print("Đã có schema; không import lại.")
                elif not empty:
                    print("Dừng: cơ sở dữ liệu không rỗng.")
                    return 1
                else:
                    conn.execute((ROOT / "database" / "init.sql").read_text(encoding="utf-8"))
                    print("Đã khởi tạo từ nguyên bản database/init.sql.")
            elif args.command == "clean-files":
                import re
                import time
                keys = {r[0] for r in conn.execute("SELECT storage_key FROM qlcv.attachments")}
                folder = Path(config["UPLOAD_FOLDER"])
                candidates = [p for p in folder.glob("*") if re.fullmatch(r"[a-f0-9]{32}", p.name)
                              and p.name not in keys and p.is_file() and time.time() - p.stat().st_mtime > 86400]
                for path in candidates:
                    print(path.name)
                    if args.apply:
                        path.unlink()
                print(f"{'Đã xóa' if args.apply else 'Có thể dọn'} {len(candidates)} tệp mồ côi trên 24 giờ.")
    except (psycopg.Error, OSError, RuntimeError):
        print("Không hoàn tất. Kiểm tra dịch vụ PostgreSQL, quyền, .env và schema; không hiển thị thông tin kết nối.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
