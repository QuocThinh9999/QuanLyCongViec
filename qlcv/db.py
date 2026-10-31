from flask import current_app, g
from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.engine import URL

TABLES = ("departments", "users", "projects", "project_members", "tasks",
          "task_members", "attachments", "audit_logs", "project_progress", "dashboard_summary")


def make_engine(pg):
    options = dict(pg)
    url = URL.create("postgresql+psycopg", username=options.pop("user"),
                     password=options.pop("password"), host=options.pop("host"),
                     port=int(options.pop("port", 5432)), database=options.pop("dbname"))
    return create_engine(url, connect_args=options, pool_pre_ping=True,
                         hide_parameters=True, echo=False)


def init_db(app):
    engine = make_engine(app.config["PG_CONFIG"])
    metadata = MetaData(schema="qlcv")
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        if not conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='qlcv')")):
            raise RuntimeError("Chưa có schema qlcv. Chạy công cụ kiểm tra/khởi tạo trong README.")
        tables = {name: Table(name, metadata, autoload_with=conn) for name in TABLES}
    app.extensions["engine"] = engine
    app.extensions["tables"] = tables


def table(name):
    return current_app.extensions["tables"][name]


def connection():
    if "conn" not in g:
        g.conn = current_app.extensions["engine"].connect()
        g.transaction = g.conn.begin()
        # Các lệnh ghi của ứng dụng tuần tự hóa việc kiểm tra quyền và thành viên.
        if g.get("mutation"):
            g.conn.execute(text("SELECT pg_advisory_xact_lock(716328941)"))
    return g.conn


def actor():
    connection().execute(text("SELECT qlcv.set_actor(:id)"), {"id": g.user["id"]})


def commit():
    g.transaction.commit()


def close_db(error=None):
    conn = g.pop("conn", None)
    if conn is not None:
        if conn.in_transaction():
            conn.rollback()
        conn.close()
