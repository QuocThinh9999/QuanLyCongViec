import hashlib
import re
import time
from collections import defaultdict, deque
from functools import wraps
from threading import Lock

import bcrypt
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import and_, delete, func, insert, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from . import permissions as rights
from .db import actor, close_db, commit, connection, table
from .files import path_for, remove_after_commit, store

bp = Blueprint("web", __name__)
attempts = defaultdict(deque)
attempt_lock = Lock()
DUMMY_HASH = bcrypt.hashpw(b"khong-phai-mat-khau", bcrypt.gensalt())
ACTIONS = {"create": "Tạo mới", "update": "Cập nhật", "delete": "Xóa",
           "add_member": "Thêm thành viên", "remove_member": "Xóa thành viên",
           "update_progress": "Cập nhật tiến độ", "upload_file": "Tải tài liệu lên",
           "delete_file": "Xóa tài liệu", "change_role": "Đổi vai trò"}


class BusinessError(ValueError):
    pass


def require(condition):
    if not condition:
        abort(403)


def get(name, object_id):
    t = table(name)
    row = connection().execute(select(t).where(t.c.id == object_id)).mappings().first()
    if row is None:
        abort(404)
    return row


def rows(stmt):
    return connection().execute(stmt).mappings().all()


def text_field(name, limit=10000, required=False):
    value = request.form.get(name, "").strip()
    if len(value) > limit or (required and not value):
        raise BusinessError("Vui lòng nhập đầy đủ thông tin, tên tối đa 200 ký tự và nội dung tối đa 10.000 ký tự.")
    return value


def number(name):
    try:
        result = int(request.form.get(name, ""))
        if result < 1:
            raise ValueError
        return result
    except ValueError:
        raise BusinessError("Vui lòng chọn một giá trị hợp lệ.") from None


def password_hash(value):
    if not 8 <= len(value) or len(value.encode("utf-8")) > 72:
        raise BusinessError("Mật khẩu cần ít nhất 8 ký tự và tối đa 72 byte UTF-8.")
    return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def stamp(user):
    return hashlib.sha256(user["password_hash"].encode()).hexdigest()


@bp.before_app_request
def authentication():
    if request.endpoint == "static":
        return
    g.mutation = request.method == "POST" and request.endpoint not in ("web.login", "web.logout")
    g.user = None
    if session.get("user_id"):
        t = table("users")
        user = connection().execute(select(t).where(t.c.id == session["user_id"])).mappings().first()
        if user and session.get("auth_stamp") == stamp(user):
            g.user = user
        else:
            session.clear()
    if request.endpoint not in ("web.login",) and g.user is None:
        return redirect(url_for("web.login"))


def writing(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        g.new_uploads, g.remove_files = [], []
        try:
            response = fn(*args, **kwargs)
            commit()
        except BaseException as exc:
            close_db()
            # Nếu mất kết nối đúng lúc COMMIT, giữ tệp vì kết quả giao dịch có thể chưa rõ.
            # Tệp chưa được tham chiếu sẽ được công cụ dọn tệp xử lý sau 24 giờ.
            if not isinstance(exc, DBAPIError) or isinstance(exc, IntegrityError):
                remove_after_commit(g.new_uploads)
            if isinstance(exc, (BusinessError, IntegrityError, OSError, DBAPIError)):
                if isinstance(exc, BusinessError):
                    message = str(exc)
                elif isinstance(exc, OSError):
                    message = "Không thể lưu tệp. Vui lòng kiểm tra dung lượng và quyền thư mục lưu trữ."
                else:
                    state = getattr(getattr(exc, "orig", None), "sqlstate", "")
                    message = {
                        "23505": "Tên tài khoản đã tồn tại hoặc vai trò độc quyền bị trùng.",
                        "23503": "Dữ liệu đang được sử dụng. Chuyển người phụ trách và kiểm tra thành viên trước khi xóa hoặc đổi vai trò.",
                        "23514": "Thao tác chưa đáp ứng điều kiện nghiệp vụ. Phải giữ đúng 01 Admin, 01 Giám đốc và dữ liệu hợp lệ.",
                    }.get(state, "Không thể hoàn tất giao dịch. Dữ liệu đã được hoàn tác; vui lòng thử lại.")
                return render_template("error.html", code=400, message=message), 400
            raise
        remove_after_commit(g.remove_files)
        return response
    return wrapped


@bp.route("/dang-nhap", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("web.index"))
    error = None
    if request.method == "POST":
        key = request.remote_addr or "local"
        with attempt_lock:
            now = time.monotonic()
            queue = attempts[key]
            while queue and queue[0] < now - 600:
                queue.popleft()
            if len(queue) >= 10:
                abort(429)
            queue.append(now)
        u = table("users")
        user = connection().execute(select(u).where(u.c.username == request.form.get("username", ""))).mappings().first()
        candidate = request.form.get("password", "").encode("utf-8")
        valid = bcrypt.checkpw(candidate[:72], user["password_hash"].encode() if user else DUMMY_HASH)
        if user and valid and len(candidate) <= 72:
            session.clear()
            session["user_id"] = user["id"]
            session["auth_stamp"] = stamp(user)
            session.permanent = True
            with attempt_lock:
                attempts.pop(key, None)
            return redirect(url_for("web.index"))
        error = "Tên đăng nhập hoặc mật khẩu không đúng."
    return render_template("login.html", error=error)


@bp.post("/dang-xuat")
def logout():
    session.clear()
    return redirect(url_for("web.login"))


@bp.get("/")
def index():
    return redirect(url_for("web.dashboard" if g.user["role"] in ("admin", "director") else "web.projects"))


@bp.get("/tong-quan")
def dashboard():
    require(g.user["role"] in ("admin", "director"))
    summary = connection().execute(select(table("dashboard_summary"))).mappings().one()
    p = table("project_progress")
    projects = rows(select(p).order_by(p.c.project_id))
    chart = {"names": [x["name"] for x in projects], "progress": [float(x["progress"]) for x in projects],
             "counts": [summary[k] for k in ("not_started_tasks", "in_progress_tasks", "completed_tasks")]}
    return render_template("dashboard.html", summary=summary, chart=chart)


def project_options():
    p = table("projects")
    return rows(select(p.c.id, p.c.name).order_by(p.c.name))


def employee_options(project_id=None):
    u = table("users")
    stmt = select(u.c.id, u.c.full_name, u.c.username).where(u.c.role == "employee")
    if project_id is not None:
        pm = table("project_members")
        stmt = stmt.join(pm, and_(pm.c.user_id == u.c.id, pm.c.project_id == project_id))
    return rows(stmt.order_by(u.c.full_name))


def member_options(project_id=None):
    if g.user["role"] != "admin":
        return employee_options(project_id)
    u = table("users")
    stmt = select(u.c.id, u.c.full_name, u.c.role)
    if project_id is not None:
        pm = table("project_members")
        stmt = stmt.join(pm, and_(pm.c.user_id == u.c.id, pm.c.project_id == project_id))
    return rows(stmt.order_by(u.c.full_name))


def list_tasks(project_id):
    t = table("tasks")
    result = []
    for item in rows(select(t).where(t.c.project_id == project_id).order_by(t.c.id.desc())):
        row = {"name": item["name"], "progress": item["progress"]}
        if rights.view(g.user, "task", item):
            row["id"] = item["id"]
        result.append(row)
    return result


def members(kind, object_id):
    m, u = table(kind + "_members"), table("users")
    return rows(select(u.c.id, u.c.full_name, u.c.role).join(m, m.c.user_id == u.c.id)
                .where(m.c[kind + "_id"] == object_id).order_by(u.c.full_name))


def history(project_id=None, task_id=None):
    a = table("audit_logs")
    # Lịch sử dự án không làm lộ nội dung công việc mà người xem chưa được truy cập.
    stmt = select(a.c.occurred_at, a.c.actor_full_name, a.c.actor_username,
                  a.c.actor_role, a.c.action, a.c.entity_name, a.c.entity_type)
    if task_id is not None:
        stmt = stmt.where(a.c.task_id == task_id)
    elif project_id is not None:
        stmt = stmt.where(a.c.project_id == project_id, a.c.task_id.is_(None))
    page = request.args.get("trang", 1, type=int)
    page = max(1, page)
    data = rows(stmt.order_by(a.c.id.desc()).offset((page - 1) * 50).limit(51))
    return data[:50], len(data) > 50, page


@bp.get("/du-an")
def projects():
    p, v = table("projects"), table("project_progress")
    data = []
    for item in rows(select(p, v.c.progress).join(v, v.c.project_id == p.c.id).order_by(p.c.id.desc())):
        row = {"name": item["name"], "progress": item["progress"]}
        if rights.view(g.user, "project", item):
            row.update(id=item["id"], description=item["description"])
        data.append(row)
    return render_template("projects.html", projects=data, can_create=rights.create(g.user))


@bp.get("/du-an/<int:object_id>")
def project_detail(object_id):
    obj = get("projects", object_id)
    require(rights.view(g.user, "project", obj))
    v, a, t = table("project_progress"), table("attachments"), table("tasks")
    progress = connection().scalar(select(v.c.progress).where(v.c.project_id == object_id))
    files = [dict(x, can_delete=rights.delete_file(g.user, x, obj)) for x in rows(select(a).where(a.c.project_id == object_id).order_by(a.c.id.desc()))]
    return render_template("project_detail.html", obj=obj, progress=progress, tasks=list_tasks(object_id),
                           members=members("project", object_id), files=files,
                           can_edit=rights.edit(g.user, obj), can_manage=rights.create(g.user),
                           can_delete=rights.delete_project(g.user, obj) and not connection().scalar(select(func.count()).select_from(t).where(t.c.project_id == object_id)),
                           can_upload=rights.upload(g.user, "project_shared", obj),
                           history=history(project_id=object_id), actions=ACTIONS)


@bp.route("/du-an/tao", methods=["GET", "POST"])
@writing
def project_create():
    require(rights.create(g.user))
    if request.method == "GET":
        # Không có ghi dữ liệu ở GET; decorator chỉ kết thúc giao dịch đọc.
        return render_template("object_form.html", kind="project", obj=None)
    name, description = text_field("name", 200, True), text_field("description")
    actor()
    p = table("projects")
    object_id = connection().scalar(insert(p).values(name=name, description=description).returning(p.c.id))
    if g.user["role"] == "department_head":
        connection().execute(insert(table("project_members")).values(project_id=object_id, user_id=g.user["id"]))
    flash("Đã tạo dự án.", "success")
    return redirect(url_for("web.project_detail", object_id=object_id))


@bp.route("/du-an/<int:object_id>/sua", methods=["GET", "POST"])
@writing
def project_edit(object_id):
    obj = get("projects", object_id)
    require(rights.edit(g.user, obj))
    if request.method == "GET":
        require(rights.view(g.user, "project", obj))
        return render_template("object_form.html", kind="project", obj=obj)
    name, description = text_field("name", 200, True), text_field("description")
    actor()
    connection().execute(update(table("projects")).where(table("projects").c.id == object_id).values(name=name, description=description))
    flash("Đã cập nhật dự án.", "success")
    return redirect(url_for("web.project_detail", object_id=object_id))


@bp.post("/du-an/<int:object_id>/xoa")
@writing
def project_delete(object_id):
    obj = get("projects", object_id)
    require(rights.delete_project(g.user, obj))
    t, a = table("tasks"), table("attachments")
    if connection().scalar(select(func.count()).select_from(t).where(t.c.project_id == object_id)):
        raise BusinessError("Chỉ được xóa dự án chưa có công việc.")
    g.remove_files = list(connection().scalars(select(a.c.storage_key).where(a.c.project_id == object_id)))
    actor()
    connection().execute(delete(table("projects")).where(table("projects").c.id == object_id))
    flash("Đã xóa dự án và tài liệu; lịch sử vẫn được giữ lại.", "success")
    return redirect(url_for("web.projects"))


@bp.route("/cong-viec/tao", methods=["GET", "POST"])
@writing
def task_create():
    require(rights.create(g.user))
    if request.method == "GET":
        project_id = request.args.get("du_an", type=int)
        return render_template("object_form.html", kind="task", obj=None, projects=project_options(),
                               employees=employee_options(), selected_project=project_id)
    project_id, assignee_id = number("project_id"), number("assignee_id")
    get("projects", project_id)
    employee = get("users", assignee_id)
    pm = table("project_members")
    if employee["role"] != "employee" or not connection().scalar(select(pm.c.user_id).where(pm.c.project_id == project_id, pm.c.user_id == assignee_id)):
        raise BusinessError("Người phụ trách phải là Nhân viên đã tham gia dự án.")
    name, description = text_field("name", 200, True), text_field("description")
    actor()
    if g.user["role"] == "department_head" and not rights.member(g.user, "project", project_id):
        # Thành viên công việc bắt buộc thuộc dự án theo khóa ngoại ghép.
        connection().execute(insert(pm).values(project_id=project_id, user_id=g.user["id"]))
    t = table("tasks")
    object_id = connection().scalar(insert(t).values(project_id=project_id, assignee_id=assignee_id,
                                                    name=name, description=description).returning(t.c.id))
    member_ids = {assignee_id}
    if g.user["role"] == "department_head":
        member_ids.add(g.user["id"])
    connection().execute(insert(table("task_members")), [dict(task_id=object_id, project_id=project_id, user_id=i) for i in sorted(member_ids)])
    flash("Đã tạo công việc và các thành viên bắt buộc.", "success")
    return redirect(url_for("web.task_detail", object_id=object_id))


@bp.get("/cong-viec/<int:object_id>")
def task_detail(object_id):
    obj = get("tasks", object_id)
    require(rights.view(g.user, "task", obj))
    a = table("attachments")
    files = [dict(x, can_delete=rights.delete_file(g.user, x, obj)) for x in rows(select(a).where(a.c.task_id == object_id).order_by(a.c.id.desc()))]
    return render_template("task_detail.html", obj=obj, project=get("projects", obj["project_id"]),
                           assignee=get("users", obj["assignee_id"]), members=members("task", object_id), files=files,
                           can_edit=rights.edit(g.user, obj), can_manage=rights.create(g.user),
                           can_progress=rights.progress(g.user, obj),
                           can_delete=g.user["role"] == "admin" and obj["progress"] == 0,
                           can_upload_shared=rights.upload(g.user, "task_shared", obj),
                           can_upload_private=rights.upload(g.user, "task_private", obj),
                           history=history(task_id=object_id), actions=ACTIONS)


@bp.route("/cong-viec/<int:object_id>/sua", methods=["GET", "POST"])
@writing
def task_edit(object_id):
    obj = get("tasks", object_id)
    require(rights.edit(g.user, obj))
    if request.method == "GET":
        require(rights.view(g.user, "task", obj))
        task_employees = [x for x in members("task", object_id) if x["role"] == "employee"]
        return render_template("object_form.html", kind="task", obj=obj, employees=task_employees)
    assignee_id = number("assignee_id")
    target = get("users", assignee_id)
    m = table("task_members")
    if target["role"] != "employee" or not connection().scalar(select(m.c.user_id).where(m.c.task_id == object_id, m.c.user_id == assignee_id)):
        raise BusinessError("Người phụ trách phải là Nhân viên thuộc công việc. Thêm thành viên trước khi chuyển người phụ trách.")
    name, description = text_field("name", 200, True), text_field("description")
    actor()
    connection().execute(update(table("tasks")).where(table("tasks").c.id == object_id).values(name=name, description=description, assignee_id=assignee_id))
    flash("Đã cập nhật công việc.", "success")
    return redirect(url_for("web.task_detail", object_id=object_id))


@bp.post("/cong-viec/<int:object_id>/tien-do")
@writing
def task_progress(object_id):
    obj = get("tasks", object_id)
    require(rights.progress(g.user, obj))
    from decimal import Decimal, InvalidOperation
    try:
        value = Decimal(request.form.get("progress", ""))
        if not value.is_finite() or not 0 <= value <= 100 or value.as_tuple().exponent < -2:
            raise InvalidOperation
    except InvalidOperation:
        raise BusinessError("Tiến độ phải từ 0 đến 100%, tối đa hai chữ số thập phân.") from None
    actor()
    connection().execute(update(table("tasks")).where(table("tasks").c.id == object_id).values(progress=value))
    flash("Đã cập nhật tiến độ.", "success")
    return redirect(url_for("web.task_detail", object_id=object_id))


@bp.post("/cong-viec/<int:object_id>/xoa")
@writing
def task_delete(object_id):
    require(g.user["role"] == "admin")
    obj = get("tasks", object_id)
    if obj["progress"] != 0:
        raise BusinessError("Chỉ được xóa công việc có tiến độ 0%.")
    a = table("attachments")
    g.remove_files = list(connection().scalars(select(a.c.storage_key).where(a.c.task_id == object_id)))
    actor()
    connection().execute(delete(table("tasks")).where(table("tasks").c.id == object_id))
    flash("Đã xóa công việc và tài liệu; lịch sử vẫn được giữ lại.", "success")
    return redirect(url_for("web.project_detail", object_id=obj["project_id"]))


@bp.route("/thanh-vien/<kind>/<int:object_id>", methods=["GET", "POST"])
@writing
def membership(kind, object_id):
    require(rights.create(g.user))
    if kind not in ("project", "task"):
        abort(404)
    obj = get("projects" if kind == "project" else "tasks", object_id)
    # Quyền thêm Nhân viên của TBP không bị giới hạn theo bộ phận/người tạo.
    if request.method == "GET":
        can_view = rights.view(g.user, kind, obj)
        data = members(kind, object_id) if can_view else []
        return render_template("members.html", kind=kind, obj_name=obj["name"], object_id=object_id, members=data,
                               can_view=can_view,
                               employees=member_options(obj["project_id"] if kind == "task" and can_view else None))
    user_id = number("user_id")
    target = get("users", user_id)
    if g.user["role"] != "admin" and target["role"] != "employee":
        raise BusinessError("Trưởng bộ phận chỉ được thêm hoặc gỡ Nhân viên.")
    m = table(kind + "_members")
    condition = and_(m.c[kind + "_id"] == object_id, m.c.user_id == user_id)
    exists = connection().scalar(select(m.c.user_id).where(condition)) is not None
    operation = request.form.get("operation", "add")
    if operation not in ("add", "remove"):
        raise BusinessError("Thao tác thành viên không hợp lệ.")
    if operation == "remove":
        t = table("tasks")
        linked = (t.c.project_id == object_id) if kind == "project" else (t.c.id == object_id)
        if connection().scalar(select(t.c.id).where(linked, t.c.assignee_id == user_id).limit(1)):
            raise BusinessError("Phải chuyển người phụ trách trước khi gỡ thành viên này.")
    elif kind == "task":
        pm = table("project_members")
        if not connection().scalar(select(pm.c.user_id).where(pm.c.project_id == obj["project_id"], pm.c.user_id == user_id)):
            raise BusinessError("Nhân viên phải thuộc dự án trước khi thêm vào công việc.")
    actor()
    if operation == "remove" and exists:
        connection().execute(delete(m).where(condition))
    elif operation == "add" and not exists:
        value = {kind + "_id": object_id, "user_id": user_id}
        if kind == "task":
            value["project_id"] = obj["project_id"]
        connection().execute(insert(m).values(**value))
    flash("Đã cập nhật thành viên.", "success")
    return redirect(url_for("web.membership", kind=kind, object_id=object_id))


@bp.get("/thanh-vien")
def membership_picker():
    require(rights.create(g.user))
    # Chỉ tên đối tượng để chọn nơi thêm thành viên; không trả mô tả/người tạo.
    t = table("tasks")
    return render_template("membership_picker.html", projects=project_options(), tasks=rows(select(t.c.id, t.c.name).order_by(t.c.name)))


@bp.post("/tai-lieu/<kind>/<int:object_id>/tai-len")
@writing
def upload(kind, object_id):
    if kind not in ("project_shared", "task_shared", "task_private"):
        abort(404)
    is_project = kind == "project_shared"
    obj = get("projects" if is_project else "tasks", object_id)
    require(rights.upload(g.user, kind, obj))
    uploaded = request.files.get("file")
    name = (uploaded.filename or "").replace("\\", "/").split("/")[-1].strip() if uploaded else ""
    if not name or len(name) > 255 or any(ord(c) < 32 for c in name):
        raise BusinessError("Chọn tệp có tên hợp lệ, tối đa 255 ký tự.")
    actor()
    key, size = store(uploaded)
    g.new_uploads.append(key)
    connection().execute(insert(table("attachments")).values(kind=kind, project_id=object_id if is_project else None,
                          task_id=None if is_project else object_id, original_filename=name, storage_key=key,
                          mime_type=uploaded.mimetype or "application/octet-stream", size_bytes=size))
    flash("Đã tải tài liệu lên.", "success")
    return redirect(url_for("web.project_detail" if is_project else "web.task_detail", object_id=object_id))


def attachment_context(object_id):
    attachment = get("attachments", object_id)
    is_project = attachment["kind"] == "project_shared"
    obj = get("projects" if is_project else "tasks", attachment["project_id"] if is_project else attachment["task_id"])
    return attachment, obj, is_project


@bp.get("/tai-lieu/<int:object_id>")
def download(object_id):
    attachment, obj, is_project = attachment_context(object_id)
    require(rights.view(g.user, "project" if is_project else "task", obj))
    try:
        path = path_for(attachment["storage_key"])
    except ValueError:
        abort(404)
    if not path.is_file():
        abort(404)
    # Luôn tải xuống để tệp HTML/SVG do người dùng cung cấp không chạy cùng nguồn.
    return send_file(path, as_attachment=True, download_name=attachment["original_filename"], mimetype="application/octet-stream", max_age=0)


@bp.post("/tai-lieu/<int:object_id>/xoa")
@writing
def attachment_delete(object_id):
    attachment, obj, is_project = attachment_context(object_id)
    require(rights.delete_file(g.user, attachment, obj))
    actor()
    connection().execute(delete(table("attachments")).where(table("attachments").c.id == object_id))
    g.remove_files.append(attachment["storage_key"])
    flash("Đã xóa tài liệu.", "success")
    return redirect(url_for("web.project_detail" if is_project else "web.task_detail", object_id=obj["id"]))


@bp.get("/tai-khoan")
def users():
    require(g.user["role"] == "admin")
    u, d = table("users"), table("departments")
    data = rows(select(u.c.id, u.c.username, u.c.full_name, u.c.role, d.c.name.label("department"))
                .outerjoin(d, d.c.id == u.c.department_id).order_by(u.c.id))
    return render_template("users.html", users=data)


@bp.get("/tai-khoan/<int:object_id>")
def user_detail(object_id):
    require(g.user["role"] == "admin")
    obj = get("users", object_id)
    d = table("departments")
    return render_template("user_detail.html", obj=obj,
                           department=connection().scalar(select(d.c.name).where(d.c.id == obj["department_id"])))


def user_values(old=None):
    username = text_field("username", 50, True)
    if not re.fullmatch(r"[a-z0-9_]{3,50}", username):
        raise BusinessError("Tên đăng nhập gồm 3–50 chữ thường không dấu, chữ số hoặc dấu gạch dưới.")
    role = request.form.get("role", "")
    if role not in rights.ROLES:
        raise BusinessError("Vai trò không hợp lệ.")
    if (not old or old["role"] != role) and (role in ("admin", "director") or (old and old["role"] in ("admin", "director"))):
        raise BusinessError("Dùng chức năng chuyển vai trò để giữ đúng 01 Admin và 01 Giám đốc.")
    values = dict(username=username, full_name=text_field("full_name", 200, True), role=role,
                  department_id=None if role in ("admin", "director") else number("department_id"))
    if values["department_id"] is not None:
        get("departments", values["department_id"])
    password = request.form.get("password", "")
    if password or not old:
        values["password_hash"] = password_hash(password)
    return values


@bp.route("/tai-khoan/tao", methods=["GET", "POST"])
@writing
def user_create():
    require(g.user["role"] == "admin")
    if request.method == "GET":
        return render_template("user_form.html", obj=None, departments=rows(select(table("departments"))))
    values = user_values()
    actor()
    u = table("users")
    object_id = connection().scalar(insert(u).values(**values).returning(u.c.id))
    flash("Đã tạo tài khoản.", "success")
    return redirect(url_for("web.user_detail", object_id=object_id))


@bp.route("/tai-khoan/<int:object_id>/sua", methods=["GET", "POST"])
@writing
def user_edit(object_id):
    require(g.user["role"] == "admin")
    obj = get("users", object_id)
    if request.method == "GET":
        return render_template("user_form.html", obj=obj, departments=rows(select(table("departments"))))
    values = user_values(obj)
    if obj["role"] == "employee" and values["role"] != "employee":
        t = table("tasks")
        if connection().scalar(select(t.c.id).where(t.c.assignee_id == object_id).limit(1)):
            raise BusinessError("Chuyển người phụ trách trước khi đổi vai trò của Nhân viên.")
    actor()
    connection().execute(update(table("users")).where(table("users").c.id == object_id).values(**values))
    if object_id == g.user["id"] and "password_hash" in values:
        session["auth_stamp"] = hashlib.sha256(values["password_hash"].encode()).hexdigest()
    flash("Đã cập nhật tài khoản. Quyền được áp dụng ngay ở yêu cầu tiếp theo.", "success")
    return redirect(url_for("web.user_detail", object_id=object_id))


@bp.post("/tai-khoan/<int:object_id>/xoa")
@writing
def user_delete(object_id):
    require(g.user["role"] == "admin")
    obj = get("users", object_id)
    if obj["role"] in ("admin", "director"):
        raise BusinessError("Chuyển vai trò độc quyền sang tài khoản khác trước khi xóa tài khoản này.")
    t = table("tasks")
    if connection().scalar(select(t.c.id).where(t.c.assignee_id == object_id).limit(1)):
        raise BusinessError("Tài khoản đang phụ trách công việc. Chuyển người phụ trách trước khi xóa.")
    actor()
    connection().execute(delete(table("users")).where(table("users").c.id == object_id))
    flash("Đã xóa tài khoản; dự án, công việc, tài liệu và lịch sử được giữ lại.", "success")
    return redirect(url_for("web.users"))


@bp.route("/tai-khoan/chuyen-vai-tro", methods=["GET", "POST"])
@writing
def role_transfer():
    require(g.user["role"] == "admin")
    u = table("users")
    if request.method == "GET":
        return render_template("role_transfer.html", users=rows(select(u.c.id, u.c.full_name, u.c.role).order_by(u.c.full_name)))
    role = request.form.get("role", "")
    if role not in ("admin", "director"):
        raise BusinessError("Chỉ chuyển vai trò Admin hoặc Giám đốc bằng chức năng này.")
    target = get("users", number("target_id"))
    if target["role"] == role:
        raise BusinessError("Tài khoản đã giữ vai trò này. Vui lòng chọn người nhận khác.")
    t = table("tasks")
    if connection().scalar(select(t.c.id).where(t.c.assignee_id == target["id"]).limit(1)):
        raise BusinessError("Chuyển các công việc đang phụ trách trước khi nhận vai trò mới.")
    holder = connection().execute(select(u).where(u.c.role == role)).mappings().one()
    actor()
    # Hoán đổi nguyên tử; UNIQUE và trigger được kiểm tra ở cuối giao dịch.
    connection().execute(update(u).where(u.c.id == holder["id"]).values(role=target["role"], department_id=target["department_id"]))
    connection().execute(update(u).where(u.c.id == target["id"]).values(role=role, department_id=None))
    flash("Đã chuyển vai trò và hoán đổi vai trò/bộ phận với người nhận.", "success")
    return redirect(url_for("web.index"))


@bp.get("/lich-su")
def audit():
    require(g.user["role"] == "admin")
    return render_template("audit.html", history=history(), actions=ACTIONS)
