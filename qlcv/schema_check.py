"""Đọc hợp đồng schema để đối chiếu với bản SQL đầu vào trong CSDL kiểm thử."""


def contract(conn):
    queries = {
        "columns": """SELECT table_name,column_name,ordinal_position,udt_name,is_nullable,column_default,is_identity,identity_generation,is_generated,generation_expression
            FROM information_schema.columns WHERE table_schema='qlcv' ORDER BY table_name,ordinal_position""",
        "constraints": """SELECT c.relname,k.conname,pg_get_constraintdef(k.oid) FROM pg_constraint k
            JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='qlcv' ORDER BY c.relname,k.conname""",
        "indexes": "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='qlcv' ORDER BY tablename,indexname",
        "triggers": """SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t
            JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='qlcv' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname""",
        "functions": """SELECT p.proname,pg_get_function_arguments(p.oid),pg_get_functiondef(p.oid)
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='qlcv' ORDER BY p.proname""",
        "views": "SELECT table_name,view_definition FROM information_schema.views WHERE table_schema='qlcv' ORDER BY table_name",
        "enums": """SELECT t.typname,e.enumlabel FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid
            JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='qlcv' ORDER BY t.typname,e.enumsortorder""",
    }
    return {name: conn.execute(query).fetchall() for name, query in queries.items()}
