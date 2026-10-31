import io
import re
from pathlib import Path

import bcrypt
import psycopg
import pytest

from .conftest import PASSWORD


@pytest.mark.parametrize("username,role", [("admin","admin"),("giamdoc","director"),("tbp_phanmem","department_head"),("phanmem_nv01","employee")])
def test_login_four_roles(env, username, role):
    client = env.login(username)
    assert client.get("/du-an").status_code == 200
    assert client.get("/tong-quan").status_code == (200 if role in ("admin","director") else 403)
    assert client.get("/tai-khoan").status_code == (200 if role == "admin" else 403)
    assert client.post("/dang-xuat").status_code == 302
    assert client.get("/du-an").status_code == 302


def test_auth_csrf_and_no_registration(env):
    client = env.app.test_client()
    assert client.get("/du-an/1").status_code == 302
    assert client.get("/dang-ky").status_code == 302
    env.app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/dang-nhap", data={"username": "admin", "password": PASSWORD}).status_code == 400
    page = client.get("/dang-nhap")
    token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
    assert client.post("/dang-nhap", data={"username":"admin","password":PASSWORD,"csrf_token":token}).status_code == 302
    assert client.post("/du-an/tao", data={"name":"Trái phép"}).status_code == 400
    assert env.query("SELECT count(*) FROM qlcv.projects")[0][0] == 0


@pytest.mark.parametrize("username", ["giamdoc","phanmem_nv01"])
def test_no_write_rights_from_viewing(env, work, username):
    p,t = work
    c = env.login(username)
    assert c.post("/du-an/tao",data={"name":"Sai"}).status_code == 403
    assert c.post(f"/du-an/{p}/sua",data={"name":"Sai"}).status_code == 403
    assert c.post("/cong-viec/tao",data={"project_id":p,"assignee_id":9,"name":"Sai"}).status_code == 403
    assert c.post(f"/cong-viec/{t}/sua",data={"name":"Sai","assignee_id":9}).status_code == 403
    assert c.post(f"/cong-viec/{t}/xoa").status_code == 403
    assert c.post(f"/thanh-vien/project/{p}",data={"user_id":6}).status_code == 403
    assert c.post("/tai-khoan/tao",data={}).status_code == 403


def test_visibility_and_direct_urls(env, work):
    p,t = work
    c = env.login("phancung_nv01")
    response = c.get("/du-an")
    text = response.get_data(as_text=True)
    assert "Dự án A" in text and "0%" in text
    assert "NỘI DUNG DỰ ÁN BÍ MẬT" not in text
    assert f'href="/du-an/{p}"' not in text
    assert c.get(f"/du-an/{p}").status_code == 403
    assert c.get(f"/cong-viec/{t}").status_code == 403
    c = env.login("phanmem_nv02")
    response = c.get(f"/du-an/{p}")
    text = response.get_data(as_text=True)
    assert "Công việc A" in text
    assert "NỘI DUNG CÔNG VIỆC BÍ MẬT" not in text
    assert f'href="/cong-viec/{t}"' not in text
    assert c.get(f"/cong-viec/{t}").status_code == 403
    for who in ("admin", "giamdoc"):
        assert env.login(who).get(f"/cong-viec/{t}").status_code == 200


def test_tbp_creator_edit_and_defaults(env, work):
    p,t = work
    owner, other = env.login("tbp_phanmem"), env.login("tbp_phancung")
    assert (env.ids['tbp_phanmem'],) in env.query("SELECT user_id FROM qlcv.project_members WHERE project_id=%s",(p,))
    assert (env.ids['tbp_phanmem'],) in env.query("SELECT user_id FROM qlcv.task_members WHERE task_id=%s",(t,))
    assert owner.post(f"/du-an/{p}/sua",data={"name":"Tên mới","description":"Mới"}).status_code == 302
    assert other.post(f"/du-an/{p}/sua",data={"name":"Sai"}).status_code == 403
    assert other.post(f"/cong-viec/{t}/sua",data={"name":"Sai","assignee_id":9}).status_code == 403
    # TBP khác được tạo công việc; phải vào dự án cùng giao dịch để thỏa khóa ngoại.
    response = other.post("/cong-viec/tao",data={"project_id":p,"assignee_id":env.ids['phanmem_nv01'],"name":"Việc khác"})
    assert response.status_code == 302
    new = int(response.location.rsplit("/",1)[-1])
    assert (env.ids['tbp_phancung'],) in env.query("SELECT user_id FROM qlcv.project_members WHERE project_id=%s",(p,))
    assert (env.ids['tbp_phancung'],) in env.query("SELECT user_id FROM qlcv.task_members WHERE task_id=%s",(new,))


def test_membership_and_assignee_constraints(env, work):
    p,t = work
    c = env.login("admin")
    outsider,assignee = env.ids['admin_nv01'],env.ids['phanmem_nv01']
    assert c.post(f"/thanh-vien/task/{t}",data={"user_id":outsider}).status_code == 400
    assert c.post(f"/thanh-vien/project/{p}",data={"user_id":outsider}).status_code == 302
    assert c.post(f"/thanh-vien/task/{t}",data={"user_id":outsider}).status_code == 302
    assert c.post(f"/thanh-vien/task/{t}",data={"user_id":env.ids['tbp_phanmem']}).status_code == 302
    assert env.login("tbp_phanmem").post(f"/thanh-vien/task/{t}",data={"user_id":env.ids['tbp_phancung']}).status_code == 400
    assert c.post(f"/thanh-vien/project/{p}",data={"user_id":assignee,"operation":"remove"}).status_code == 400
    assert c.post(f"/thanh-vien/task/{t}",data={"user_id":assignee,"operation":"remove"}).status_code == 400
    assert c.post(f"/cong-viec/{t}/sua",data={"name":"Công việc A","assignee_id":outsider}).status_code == 302
    assert c.post(f"/thanh-vien/project/{p}",data={"user_id":assignee,"operation":"remove"}).status_code == 302
    assert env.login("phanmem_nv01").get(f"/cong-viec/{t}").status_code == 403
    assert env.query("SELECT count(*) FROM qlcv.task_members WHERE task_id=%s AND user_id=%s",(t,assignee))[0][0] == 0


@pytest.mark.parametrize("who,expected", [("admin",302),("giamdoc",403),("tbp_phanmem",302),("tbp_phancung",403),("phanmem_nv01",302),("phanmem_nv02",403)])
def test_progress_permission(env, work, who, expected):
    _,t = work
    assert env.login(who).post(f"/cong-viec/{t}/tien-do",data={"progress":"37.25"}).status_code == expected


@pytest.mark.parametrize("value", ["-1","101","NaN","Infinity","abc","0.001"])
def test_invalid_progress(env, work, value):
    _,t = work
    assert env.login().post(f"/cong-viec/{t}/tien-do",data={"progress":value}).status_code == 400
    assert env.query("SELECT progress FROM qlcv.tasks WHERE id=%s",(t,))[0][0] == 0


def test_project_progress_dashboard_delete(env, work):
    p,t = work
    c = env.login()
    assert c.post(f"/du-an/{p}/xoa").status_code == 400
    c.post(f"/cong-viec/{t}/tien-do",data={"progress":"100"})
    assert c.post(f"/cong-viec/{t}/xoa").status_code == 400
    r = c.post("/cong-viec/tao",data={"project_id":p,"assignee_id":env.ids['phanmem_nv01'],"name":"Công việc B"})
    t2 = int(r.location.rsplit("/",1)[-1])
    assert env.query("SELECT progress FROM qlcv.project_progress WHERE project_id=%s",(p,))[0][0] == 50
    summary = env.query("SELECT total_tasks,not_started_tasks,in_progress_tasks,completed_tasks FROM qlcv.dashboard_summary")[0]
    assert summary == (2,1,0,1)
    assert c.post(f"/cong-viec/{t2}/xoa").status_code == 302
    assert env.query("SELECT progress FROM qlcv.project_progress WHERE project_id=%s",(p,))[0][0] == 100
    c.post(f"/cong-viec/{t}/tien-do",data={"progress":0})
    assert c.post(f"/cong-viec/{t}/xoa").status_code == 302
    assert env.query("SELECT progress FROM qlcv.project_progress WHERE project_id=%s",(p,))[0][0] == 0
    assert c.post(f"/du-an/{p}/xoa").status_code == 302
    assert env.query("SELECT count(*) FROM qlcv.audit_logs WHERE entity_type='projects' AND action='delete'")[0][0] == 1


def test_empty_dashboard(env):
    text = env.login().get("/tong-quan").get_data(as_text=True)
    assert text.count("Chưa có dữ liệu") == 2


@pytest.mark.parametrize("who,kind,expected", [
    ("admin","project_shared",302),("giamdoc","project_shared",403),
    ("tbp_phanmem","project_shared",302),("phanmem_nv02","project_shared",302),
    ("phancung_nv01","project_shared",403), ("tbp_phanmem","task_shared",302),
    ("phanmem_nv01","task_private",302),("tbp_phanmem","task_private",403),
    ("phanmem_nv02","task_shared",403),("giamdoc","task_private",403),
    ("admin","task_private",302),
])
def test_upload_rules(env, work, who, kind, expected):
    p,t = work
    obj = p if kind == "project_shared" else t
    response = env.login(who).post(f"/tai-lieu/{kind}/{obj}/tai-len",data={"file":(io.BytesIO(b"noi dung"),"tài liệu.txt")})
    assert response.status_code == expected


def test_private_visibility_delete_and_revocation(env, work):
    p,t = work
    owner = env.login("phanmem_nv01")
    assert owner.post(f"/tai-lieu/task_private/{t}/tai-len",data={"file":(io.BytesIO(b"bi mat"),"../../tài liệu.html")}).status_code == 302
    file_id,key,name = env.query("SELECT id,storage_key,original_filename FROM qlcv.attachments")[0]
    assert name == "tài liệu.html" and "/" not in key and "\\" not in key
    for who,expected in (("admin",200),("giamdoc",200),("tbp_phanmem",200),("phanmem_nv02",403)):
        response = env.login(who).get(f"/tai-lieu/{file_id}")
        assert response.status_code == expected
        if expected == 200:
            assert "attachment" in response.headers["Content-Disposition"]
    assert env.login("tbp_phanmem").post(f"/tai-lieu/{file_id}/xoa").status_code == 403
    admin = env.login()
    admin.post(f"/thanh-vien/task/{t}",data={"user_id":env.ids['phanmem_nv02']})
    admin.post(f"/cong-viec/{t}/sua",data={"name":"Công việc A","assignee_id":env.ids['phanmem_nv02']})
    admin.post(f"/thanh-vien/task/{t}",data={"user_id":env.ids['phanmem_nv01'],"operation":"remove"})
    assert owner.get(f"/tai-lieu/{file_id}").status_code == 403
    assert owner.post(f"/tai-lieu/{file_id}/xoa").status_code == 403
    assert admin.post(f"/tai-lieu/{file_id}/xoa").status_code == 302
    assert not (Path(env.app.config["UPLOAD_FOLDER"]) / key).exists()


def test_account_delete_preserves_objects_and_history(env):
    admin = env.login()
    response = admin.post("/tai-khoan/tao",data={"username":"nguoi_tao","full_name":"Người đã xóa","role":"department_head","department_id":2,"password":PASSWORD})
    uid = int(response.location.rsplit("/",1)[-1])
    owner = env.login("nguoi_tao")
    response = owner.post("/du-an/tao",data={"name":"Giữ lại dự án"})
    p = int(response.location.rsplit("/",1)[-1])
    owner.post(f"/thanh-vien/project/{p}",data={"user_id":env.ids['phanmem_nv01']})
    response = owner.post("/cong-viec/tao",data={"project_id":p,"assignee_id":env.ids['phanmem_nv01'],"name":"Giữ lại công việc"})
    t = int(response.location.rsplit("/",1)[-1])
    owner.post(f"/tai-lieu/task_shared/{t}/tai-len",data={"file":(io.BytesIO(b"giu lai"),"giữ lại.txt")})
    file_id,key = env.query("SELECT id,storage_key FROM qlcv.attachments")[0]
    assert admin.post(f"/tai-khoan/{uid}/xoa").status_code == 302
    assert env.query("SELECT created_by FROM qlcv.projects WHERE id=%s",(p,)) == [(None,)]
    assert env.query("SELECT created_by FROM qlcv.tasks WHERE id=%s",(t,)) == [(None,)]
    assert env.query("SELECT uploaded_by FROM qlcv.attachments WHERE id=%s",(file_id,)) == [(None,)]
    assert (Path(env.app.config["UPLOAD_FOLDER"]) / key).is_file()
    assert env.query("SELECT count(*) FROM qlcv.audit_logs WHERE actor_id=%s AND actor_full_name='Người đã xóa'",(uid,))[0][0] > 0
    assert owner.get("/du-an").status_code == 302


def test_account_constraints_role_transfer_and_fresh_permissions(env, work):
    p,t = work
    c = env.login()
    user = env.login("phanmem_nv02")
    assert c.post(f"/tai-khoan/{env.ids['admin']}/xoa").status_code == 400
    assert c.post(f"/tai-khoan/{env.ids['giamdoc']}/xoa").status_code == 400
    assert c.post(f"/tai-khoan/{env.ids['phanmem_nv01']}/xoa").status_code == 400
    assert c.post(f"/tai-khoan/{env.ids['phanmem_nv01']}/sua",data={"username":"phanmem_nv01","full_name":"Nhân viên","role":"department_head","department_id":2}).status_code == 400
    assert c.post("/tai-khoan/chuyen-vai-tro",data={"role":"director","target_id":env.ids['phanmem_nv01']}).status_code == 400
    assert c.post("/tai-khoan/chuyen-vai-tro",data={"role":"director","target_id":env.ids['phanmem_nv02']}).status_code == 302
    assert user.get("/tong-quan").status_code == 200
    assert user.post(f"/cong-viec/{t}/tien-do",data={"progress":1}).status_code == 403
    assert env.query("SELECT role::text,count(*) FROM qlcv.users WHERE role IN ('admin','director') GROUP BY role ORDER BY role") == [("admin",1),("director",1)]
    assert c.post("/tai-khoan/chuyen-vai-tro",data={"role":"admin","target_id":env.ids['admin_nv01']}).status_code == 302
    assert c.get("/tai-khoan").status_code == 403
    assert env.login("admin_nv01").get("/tai-khoan").status_code == 200


def test_new_bcrypt_and_password_session_revocation(env):
    c = env.login()
    response = c.post("/tai-khoan/tao",data={"username":"moi_test","full_name":"Nhân viên mới","role":"employee","department_id":3,"password":PASSWORD})
    assert response.status_code == 302
    uid = int(response.location.rsplit("/",1)[-1])
    hash_value = env.query("SELECT password_hash FROM qlcv.users WHERE id=%s",(uid,))[0][0]
    assert bcrypt.checkpw(PASSWORD.encode(),hash_value.encode())
    user = env.login("moi_test")
    assert c.post(f"/tai-khoan/{uid}/sua",data={"username":"moi_test","full_name":"Nhân viên mới","role":"employee","department_id":3,"password":"MatKhauMoi2026!"}).status_code == 302
    assert user.get("/du-an").status_code == 302
    text = c.get(f"/tai-khoan/{uid}").get_data(as_text=True)
    assert hash_value not in text


def test_history_actor_immutable_and_no_read_logs(env, work):
    p,t = work
    c = env.login()
    before = env.query("SELECT count(*) FROM qlcv.audit_logs")[0][0]
    assert c.get(f"/du-an/{p}").status_code == 200
    assert c.get(f"/cong-viec/{t}").status_code == 200
    assert env.query("SELECT count(*) FROM qlcv.audit_logs")[0][0] == before
    c.post(f"/cong-viec/{t}/tien-do",data={"progress":15,"actor_id":2,"created_by":2})
    assert env.query("SELECT actor_id,action FROM qlcv.audit_logs ORDER BY id DESC LIMIT 1")[0] == (env.ids['admin'],"update_progress")
    assert env.query("SELECT count(*) FROM qlcv.audit_logs WHERE old_data ? 'password_hash' OR new_data ? 'password_hash'")[0][0] == 0
    for command in ("UPDATE qlcv.audit_logs SET entity_name='sai'", "DELETE FROM qlcv.audit_logs", "TRUNCATE qlcv.tasks"):
        with pytest.raises(psycopg.Error):
            with psycopg.connect(**env.pg) as conn:
                conn.execute(command)
    with pytest.raises(psycopg.Error):
        with psycopg.connect(**env.pg) as conn:
            conn.execute("INSERT INTO qlcv.projects(name) VALUES ('Thiếu actor')")


def test_cascade_file_delete_and_rollback(env, work):
    p,t = work
    c = env.login()
    c.post(f"/tai-lieu/task_shared/{t}/tai-len",data={"file":(io.BytesIO(b"kiem thu"),"x.txt")})
    key = env.query("SELECT storage_key FROM qlcv.attachments")[0][0]
    c.post(f"/cong-viec/{t}/tien-do",data={"progress":10})
    assert c.post(f"/cong-viec/{t}/xoa").status_code == 400
    assert (Path(env.app.config["UPLOAD_FOLDER"]) / key).exists()
    c.post(f"/cong-viec/{t}/tien-do",data={"progress":0})
    assert c.post(f"/cong-viec/{t}/xoa").status_code == 302
    assert not (Path(env.app.config["UPLOAD_FOLDER"]) / key).exists()
    assert env.query("SELECT count(*) FROM qlcv.attachments")[0][0] == 0
    assert env.query("SELECT count(*) FROM qlcv.audit_logs WHERE action='delete_file'")[0][0] == 1


def test_tbp_no_detail_leak_in_members_form(env, work):
    p,t = work
    c = env.login("tbp_phancung")
    for kind,obj in (("project",p),("task",t)):
        text = c.get(f"/thanh-vien/{kind}/{obj}").get_data(as_text=True)
        assert "NỘI DUNG" not in text
        assert "Thành viên hiện tại" not in text


@pytest.mark.parametrize("path", ["/du-an/tao","/cong-viec/tao","/tai-khoan","/tai-khoan/1","/tai-khoan/1/sua","/tai-khoan/tao","/tai-khoan/chuyen-vai-tro","/lich-su","/thanh-vien"])
def test_forms_render(env,path):
    assert env.login().get(path).status_code == 200


def test_creator_deletes_empty_project_and_other_tbp_denied(env):
    creator = env.login("tbp_phanmem")
    response = creator.post("/du-an/tao", data={"name":"Dự án chưa có việc"})
    p = int(response.location.rsplit("/",1)[-1])
    assert env.login("tbp_phancung").post(f"/du-an/{p}/xoa").status_code == 403
    assert creator.post(f"/du-an/{p}/xoa").status_code == 302


def test_admin_remove_head_revokes_access_progress_and_file_delete(env,work):
    p,t = work
    head, admin = env.login("tbp_phanmem"),env.login()
    head.post(f"/tai-lieu/task_shared/{t}/tai-len",data={"file":(io.BytesIO(b"data"),"x.txt")})
    file_id = env.query("SELECT id FROM qlcv.attachments")[0][0]
    assert admin.post(f"/thanh-vien/project/{p}",data={"user_id":env.ids['tbp_phanmem'],"operation":"remove"}).status_code == 302
    assert head.get(f"/du-an/{p}").status_code == 403
    assert head.get(f"/cong-viec/{t}").status_code == 403
    assert head.post(f"/cong-viec/{t}/tien-do",data={"progress":50}).status_code == 403
    assert head.post(f"/tai-lieu/{file_id}/xoa").status_code == 403


def test_project_file_uploader_delete_and_project_cascade(env):
    c = env.login("tbp_phanmem")
    response = c.post("/du-an/tao",data={"name":"Dự án tài liệu"})
    p = int(response.location.rsplit("/",1)[-1])
    c.post(f"/tai-lieu/project_shared/{p}/tai-len",data={"file":(io.BytesIO(b"data"),"x.txt")})
    fid,key = env.query("SELECT id,storage_key FROM qlcv.attachments")[0]
    assert c.post(f"/tai-lieu/{fid}/xoa").status_code == 302
    assert not (Path(env.app.config["UPLOAD_FOLDER"]) / key).exists()
    c.post(f"/tai-lieu/project_shared/{p}/tai-len",data={"file":(io.BytesIO(b"data"),"y.txt")})
    key = env.query("SELECT storage_key FROM qlcv.attachments")[0][0]
    assert c.post(f"/du-an/{p}/xoa").status_code == 302
    assert not (Path(env.app.config["UPLOAD_FOLDER"]) / key).exists()
    assert env.query("SELECT count(*) FROM qlcv.project_members")[0][0] == 0


def test_upload_rollback_keeps_existing_file(env,work,monkeypatch):
    p,t = work
    c = env.login()
    c.post(f"/tai-lieu/task_shared/{t}/tai-len",data={"file":(io.BytesIO(b"data"),"x.txt")})
    from qlcv import routes
    original_store = routes.store
    def conflicting_upload(upload):
        key,size = original_store(upload)
        # Gây CHECK thất bại sau khi đã ghi tệp, để kiểm tra hoàn tác tệp mới.
        return key,-1
    monkeypatch.setattr(routes,"store",conflicting_upload)
    response = c.post(f"/tai-lieu/task_shared/{t}/tai-len",data={"file":(io.BytesIO(b"new"),"y.txt")})
    assert response.status_code == 400
    assert env.query("SELECT count(*) FROM qlcv.attachments")[0][0] == 1
    assert len(list(Path(env.app.config["UPLOAD_FOLDER"]).iterdir())) == 1


def test_direct_post_assignment_and_html_escape(env,work):
    p,t = work
    c = env.login()
    response = c.post(f"/du-an/{p}/sua",data={"name":"<script>alert(1)</script>","description":"<b>nội dung</b>","created_by":999,"progress":100})
    assert response.status_code == 302
    page = c.get(f"/du-an/{p}").get_data(as_text=True)
    assert '<script>alert(1)</script>' not in page
    assert '&lt;script&gt;' in page
    assert env.query("SELECT created_by FROM qlcv.projects WHERE id=%s",(p,))[0][0] == env.ids['tbp_phanmem']
    assert env.query("SELECT progress FROM qlcv.project_progress WHERE project_id=%s",(p,))[0][0] == 0


def test_swap_admin_director_without_missing_exclusive_role(env):
    admin,director = env.login(),env.login("giamdoc")
    assert admin.post("/tai-khoan/chuyen-vai-tro",data={"role":"admin","target_id":env.ids['admin']}).status_code == 400
    assert admin.post("/tai-khoan/chuyen-vai-tro",data={"role":"admin","target_id":env.ids['giamdoc']}).status_code == 302
    assert admin.get("/tai-khoan").status_code == 403
    assert director.get("/tai-khoan").status_code == 200
    assert env.query("SELECT role::text,count(*) FROM qlcv.users WHERE role IN ('admin','director') GROUP BY role ORDER BY role") == [("admin",1),("director",1)]
