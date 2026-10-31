from sqlalchemy import select

from .db import connection, table

ROLES = {"admin": "Admin", "director": "Giám đốc", "department_head": "Trưởng bộ phận", "employee": "Nhân viên"}


def member(user, kind, object_id):
    t = table(kind + "_members")
    return connection().scalar(select(t.c.user_id).where(
        t.c[kind + "_id"] == object_id, t.c.user_id == user["id"])) is not None


def view(user, kind, obj):
    return user["role"] in ("admin", "director") or member(user, kind, obj["id"])


def create(user):
    return user["role"] in ("admin", "department_head")


def edit(user, obj):
    return user["role"] == "admin" or (user["role"] == "department_head" and obj["created_by"] == user["id"])


def delete_project(user, obj):
    return user["role"] == "admin" or obj["created_by"] == user["id"]


def progress(user, obj):
    return user["role"] == "admin" or (view(user, "task", obj) and (
        user["role"] == "department_head" or (user["role"] == "employee" and obj["assignee_id"] == user["id"])))


def upload(user, kind, obj):
    if user["role"] == "admin":
        return True
    if kind == "task_private":
        return user["role"] == "employee" and obj["assignee_id"] == user["id"] and view(user, "task", obj)
    return member(user, "project" if kind == "project_shared" else "task", obj["id"])


def delete_file(user, attachment, obj):
    kind = "project" if attachment["kind"] == "project_shared" else "task"
    return user["role"] == "admin" or (attachment["uploaded_by"] == user["id"] and view(user, kind, obj))
