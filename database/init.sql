-- Khởi tạo cơ sở dữ liệu Quản lý công việc nội bộ.
-- UTF-8; PostgreSQL 14–18; không cần extension.
-- Chạy trên cơ sở dữ liệu rỗng đã tạo trước. Không chạy lại trên dữ liệu đang dùng.
-- Xem README.md để thiết lập người thực hiện và kiểm tra quyền ở backend.

BEGIN;
SET LOCAL client_encoding = 'UTF8';

-- Không dùng IF NOT EXISTS: nếu schema đã tồn tại, toàn bộ lần import bị hủy.
CREATE SCHEMA qlcv;

CREATE TYPE qlcv.app_role AS ENUM (
    'admin', 'director', 'department_head', 'employee'
);
COMMENT ON TYPE qlcv.app_role IS
    'Bốn vai trò cố định: Admin, Giám đốc, Trưởng bộ phận, Nhân viên.';

CREATE TABLE qlcv.departments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX departments_name_unique ON qlcv.departments (lower(btrim(name)));

CREATE TABLE qlcv.users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL CHECK (username ~ '^[a-z0-9_]{3,50}$'),
    full_name text NOT NULL CHECK (btrim(full_name) <> ''),
    password_hash text NOT NULL CHECK (
        password_hash ~ '^\$2[aby]\$(0[4-9]|[12][0-9]|3[01])\$[./A-Za-z0-9]{53}$'
    ),
    role qlcv.app_role NOT NULL,
    department_id bigint REFERENCES qlcv.departments(id) ON DELETE RESTRICT,
    -- NULL cho các vai trò không độc quyền; UNIQUE cho phép nhiều NULL.
    exclusive_role qlcv.app_role GENERATED ALWAYS AS (
        CASE WHEN role IN ('admin', 'director') THEN role ELSE NULL END
    ) STORED,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT users_username_unique UNIQUE (username),
    CONSTRAINT users_id_role_unique UNIQUE (id, role),
    CONSTRAINT users_exclusive_role_unique UNIQUE (exclusive_role)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT users_department_by_role CHECK (
        (role IN ('admin', 'director') AND department_id IS NULL)
        OR (role IN ('department_head', 'employee') AND department_id IS NOT NULL)
    )
);
CREATE INDEX users_department_idx ON qlcv.users(department_id);
COMMENT ON TABLE qlcv.users IS
    'Tài khoản ứng dụng, không phải tài khoản PostgreSQL. Admin độc lập với bộ phận tên Admin.';
COMMENT ON COLUMN qlcv.users.exclusive_role IS
    'Cột kỹ thuật để ràng buộc duy nhất Admin/Giám đốc tại cuối giao dịch, cho phép hoán đổi vai trò.';

-- UNIQUE ở trên bảo đảm tối đa một; trigger này bảo đảm không được thiếu.
CREATE FUNCTION qlcv.require_exclusive_roles() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, qlcv AS $$
BEGIN
    IF (SELECT count(*) FROM qlcv.users WHERE role = 'admin') <> 1
       OR (SELECT count(*) FROM qlcv.users WHERE role = 'director') <> 1 THEN
        RAISE EXCEPTION 'Sau giao dịch phải có đúng 1 Admin và đúng 1 Giám đốc.'
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER users_require_exclusive_roles
AFTER INSERT OR UPDATE OR DELETE ON qlcv.users
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION qlcv.require_exclusive_roles();

CREATE TABLE qlcv.projects (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    description text NOT NULL DEFAULT '',
    created_by bigint REFERENCES qlcv.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX projects_creator_idx ON qlcv.projects(created_by);

CREATE TABLE qlcv.project_members (
    project_id bigint NOT NULL REFERENCES qlcv.projects(id) ON DELETE CASCADE,
    user_id bigint NOT NULL REFERENCES qlcv.users(id) ON DELETE CASCADE,
    added_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (project_id, user_id)
);
CREATE INDEX project_members_user_idx ON qlcv.project_members(user_id);

CREATE TABLE qlcv.tasks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- RESTRICT ngăn xóa dự án đang có bất kỳ công việc nào.
    project_id bigint NOT NULL REFERENCES qlcv.projects(id) ON DELETE RESTRICT,
    name text NOT NULL CHECK (btrim(name) <> ''),
    description text NOT NULL DEFAULT '',
    assignee_id bigint NOT NULL,
    -- Khóa ngoại ghép bảo đảm cả khi có các giao dịch đồng thời/thay đổi vai trò.
    assignee_role qlcv.app_role GENERATED ALWAYS AS ('employee'::qlcv.app_role) STORED,
    progress numeric(5,2) NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    created_by bigint REFERENCES qlcv.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT tasks_id_project_unique UNIQUE (id, project_id),
    CONSTRAINT tasks_employee_assignee_fk FOREIGN KEY (assignee_id, assignee_role)
        REFERENCES qlcv.users(id, role) ON DELETE RESTRICT ON UPDATE NO ACTION
);
CREATE INDEX tasks_project_idx ON qlcv.tasks(project_id);
CREATE INDEX tasks_assignee_idx ON qlcv.tasks(assignee_id);
CREATE INDEX tasks_creator_idx ON qlcv.tasks(created_by);
COMMENT ON COLUMN qlcv.tasks.assignee_role IS
    'Hằng kỹ thuật employee để khóa ngoại buộc người phụ trách luôn là Nhân viên.';

CREATE TABLE qlcv.task_members (
    task_id bigint NOT NULL,
    project_id bigint NOT NULL,
    user_id bigint NOT NULL,
    added_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (task_id, user_id),
    CONSTRAINT task_members_task_project_fk FOREIGN KEY (task_id, project_id)
        REFERENCES qlcv.tasks(id, project_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT task_members_project_member_fk FOREIGN KEY (project_id, user_id)
        REFERENCES qlcv.project_members(project_id, user_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX task_members_project_user_idx ON qlcv.task_members(project_id, user_id);
CREATE INDEX task_members_user_idx ON qlcv.task_members(user_id);
COMMENT ON COLUMN qlcv.task_members.project_id IS
    'Lặp khóa dự án để dùng hai khóa ngoại bảo đảm thành viên công việc thuộc đúng dự án.';

-- Cho phép thêm công việc rồi thêm thành viên trong cùng giao dịch.
-- Cuối giao dịch, người phụ trách bắt buộc thuộc danh sách thành viên công việc.
ALTER TABLE qlcv.tasks ADD CONSTRAINT tasks_assignee_membership_fk
    FOREIGN KEY (id, assignee_id) REFERENCES qlcv.task_members(task_id, user_id)
    ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE qlcv.attachments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind text NOT NULL CHECK (kind IN ('project_shared', 'task_shared', 'task_private')),
    project_id bigint REFERENCES qlcv.projects(id) ON DELETE CASCADE,
    task_id bigint REFERENCES qlcv.tasks(id) ON DELETE CASCADE,
    original_filename text NOT NULL CHECK (btrim(original_filename) <> ''),
    storage_key text NOT NULL UNIQUE CHECK (btrim(storage_key) <> ''),
    mime_type text NOT NULL CHECK (btrim(mime_type) <> ''),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    uploaded_by bigint REFERENCES qlcv.users(id) ON DELETE SET NULL,
    uploaded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT attachments_owner_kind CHECK (
        (kind = 'project_shared' AND project_id IS NOT NULL AND task_id IS NULL)
        OR (kind IN ('task_shared', 'task_private') AND project_id IS NULL AND task_id IS NOT NULL)
    )
);
CREATE INDEX attachments_project_idx ON qlcv.attachments(project_id);
CREATE INDEX attachments_task_idx ON qlcv.attachments(task_id);
CREATE INDEX attachments_uploader_idx ON qlcv.attachments(uploaded_by);
COMMENT ON TABLE qlcv.attachments IS
    'Chỉ lưu thông tin tệp và khóa lưu trữ; backend kiểm tra quyền và xử lý tệp vật lý.';

CREATE TABLE qlcv.audit_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    -- Không dùng khóa ngoại: vẫn nhận biết người và đối tượng sau khi bị xóa.
    actor_id bigint NOT NULL,
    actor_username text NOT NULL,
    actor_full_name text NOT NULL,
    actor_role qlcv.app_role NOT NULL,
    action text NOT NULL CHECK (action IN (
        'create', 'update', 'delete', 'add_member', 'remove_member',
        'update_progress', 'upload_file', 'delete_file', 'change_role'
    )),
    entity_type text NOT NULL CHECK (entity_type IN (
        'departments', 'users', 'projects', 'project_members',
        'tasks', 'task_members', 'attachments'
    )),
    entity_key jsonb NOT NULL,
    entity_name text NOT NULL,
    project_id bigint,
    task_id bigint,
    old_data jsonb,
    new_data jsonb,
    CHECK (old_data IS NOT NULL OR new_data IS NOT NULL)
);
CREATE INDEX audit_logs_entity_idx ON qlcv.audit_logs(entity_type, entity_key, occurred_at DESC);
CREATE INDEX audit_logs_project_idx ON qlcv.audit_logs(project_id, occurred_at DESC);
CREATE INDEX audit_logs_task_idx ON qlcv.audit_logs(task_id, occurred_at DESC);
CREATE INDEX audit_logs_actor_idx ON qlcv.audit_logs(actor_id, occurred_at DESC);
COMMENT ON TABLE qlcv.audit_logs IS
    'Lịch sử thay đổi tự động, chỉ ghi thêm; giữ tên người, khóa đối tượng và dữ liệu trước/sau, không ghi băm mật khẩu.';

-- Dữ liệu khởi tạo: đúng 3 bộ phận, 14 tài khoản. Không thêm dự án/công việc/tệp.
INSERT INTO qlcv.departments(name) VALUES ('Admin'), ('Phần mềm'), ('Phần cứng');

-- Các giá trị bcrypt thực, mỗi tài khoản có salt riêng, cost 12.
INSERT INTO qlcv.users(username, full_name, password_hash, role, department_id)
SELECT v.username, v.full_name, v.password_hash, v.role::qlcv.app_role, d.id
FROM (VALUES
    ('admin', 'Nguyễn Minh Quản', '$2a$12$nx8N.1X7Zrkpljpd3rHNq.hk7tshtkGXIf81xFvsdXGjP54PQsEYG', 'admin', NULL),
    ('giamdoc', 'Trần Quốc Hưng', '$2a$12$vqZq7JQyA8MVA.8j5JTYq.nROH5v69DYwKTAzUk8SDKEDKjtqpEKG', 'director', NULL),
    ('tbp_admin', 'Lê Hoàng Anh', '$2a$12$MeEsyOIwHxkf6qSjUzsAcuZpGwe813EDQBDiAhUuXHDBMMWYIc6Wi', 'department_head', 'Admin'),
    ('tbp_phanmem', 'Phạm Minh Tuấn', '$2a$12$BTtRCEphMdeL486h2Uy3e.W0bC9Ux.INQF5qvthqOR3GZoW3ugN3W', 'department_head', 'Phần mềm'),
    ('tbp_phancung', 'Võ Thành Đạt', '$2a$12$Mfum8pIWr050ceMnHHR0z.O/R0DyjifEqLvPYhEsEIx/wAZNKriaO', 'department_head', 'Phần cứng'),
    ('admin_nv01', 'Nguyễn Thị Mai', '$2a$12$25Va8Tn7DOzZfaLVS4IJTeVMD0Bjl7ArW/IaKupVg2hbP72N5HS/2', 'employee', 'Admin'),
    ('admin_nv02', 'Trần Văn Nam', '$2a$12$QWLvs2zK/Cgyfsl.3DZJbeUB1wBW1ooHypTWYbCz/j4EqA10.Y8tG', 'employee', 'Admin'),
    ('admin_nv03', 'Lê Ngọc Lan', '$2a$12$5qzcZo5z1O8fPlk3MIKcLuDapr6hCDaU6pIFcAZiLKuJyHh95GNj2', 'employee', 'Admin'),
    ('phanmem_nv01', 'Phạm Quốc Bảo', '$2a$12$lZHLYpzIymXU0pB4JXWpX.ZI49QyXpNM/gInXJw5Ylw2Xh32cuKCy', 'employee', 'Phần mềm'),
    ('phanmem_nv02', 'Hoàng Thị Hương', '$2a$12$vA0UJh3zohTiXdumuLG92ei2M2W.EYxPukUFHSolSHerbyL.ZL.a2', 'employee', 'Phần mềm'),
    ('phanmem_nv03', 'Đặng Minh Khoa', '$2a$12$UymT3wEed2oXiL0TXMp6r.vX.j.3T6cL0jC/6joaDM10CAg8NJOgG', 'employee', 'Phần mềm'),
    ('phancung_nv01', 'Bùi Thanh Tùng', '$2a$12$y7ClXxB21qrPqeTJBh5iQOMFlhRGHVTUWanpmI25WrczXPg9Cfvrm', 'employee', 'Phần cứng'),
    ('phancung_nv02', 'Đỗ Thị Thu', '$2a$12$S1zi3OqiZSBRO7kMZ.hpXe7WMD5dxr4lsXccL3FQKEvyplI0affku', 'employee', 'Phần cứng'),
    ('phancung_nv03', 'Huỳnh Văn Phúc', '$2a$12$lYoPK4WUkw/jMfOI18AdSumTwsD4DUySpN9dVxWZAnxhLd65GL7ri', 'employee', 'Phần cứng')
) AS v(username, full_name, password_hash, role, department_name)
LEFT JOIN qlcv.departments d ON d.name = v.department_name;

-- Backend gọi hàm này sau khi xác thực và kiểm tra quyền, trong MỖI giao dịch ghi.
-- Hàm chỉ xác định người ghi lịch sử; không thay thế xác thực hoặc phân quyền.
CREATE FUNCTION qlcv.set_actor(p_user_id bigint) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, qlcv AS $$
DECLARE
    v_actor jsonb;
BEGIN
    SELECT jsonb_build_object(
        'id', id, 'username', username, 'full_name', full_name, 'role', role,
        'transaction_id', txid_current()::text
    ) INTO v_actor FROM qlcv.users WHERE id = p_user_id;
    IF v_actor IS NULL THEN
        RAISE EXCEPTION 'Tài khoản thực hiện không tồn tại.' USING ERRCODE = '22023';
    END IF;
    PERFORM set_config('app.actor', v_actor::text, true);
END;
$$;

CREATE FUNCTION qlcv.audit_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, qlcv AS $$
DECLARE
    v_actor jsonb;
    v_old jsonb;
    v_new jsonb;
    v_row jsonb;
    v_key jsonb;
    v_action text;
    v_name text;
    v_project_id bigint;
    v_task_id bigint;
BEGIN
    v_actor := nullif(current_setting('app.actor', true), '')::jsonb;
    IF v_actor IS NULL
       OR (v_actor->>'transaction_id') IS DISTINCT FROM txid_current()::text
       OR v_actor->>'id' IS NULL OR v_actor->>'username' IS NULL
       OR v_actor->>'full_name' IS NULL OR v_actor->>'role' IS NULL THEN
        RAISE EXCEPTION 'Phải gọi qlcv.set_actor(id) trong giao dịch trước khi thay đổi dữ liệu.'
            USING ERRCODE = '22023';
    END IF;

    IF TG_OP = 'DELETE' AND TG_TABLE_NAME = 'tasks' THEN
        IF OLD.progress <> 0 THEN
            RAISE EXCEPTION 'Chỉ được xóa công việc có tiến độ 0%%.' USING ERRCODE = '23514';
        END IF;
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF TG_TABLE_NAME IN ('projects', 'tasks') THEN
            NEW.created_by := (v_actor->>'id')::bigint;
        ELSIF TG_TABLE_NAME = 'attachments' THEN
            NEW.uploaded_by := (v_actor->>'id')::bigint;
        END IF;
    ELSIF TG_OP = 'UPDATE' THEN
        IF (to_jsonb(NEW) - ARRAY['exclusive_role', 'assignee_role'])
           = (to_jsonb(OLD) - ARRAY['exclusive_role', 'assignee_role']) THEN
            RETURN NEW;
        END IF;
        -- Người tạo/người tải lên không được sửa tùy ý; FK được phép SET NULL khi xóa tài khoản.
        IF TG_TABLE_NAME IN ('projects', 'tasks') THEN
            IF NEW.created_by IS DISTINCT FROM OLD.created_by
               AND (NEW.created_by IS NOT NULL
                    OR EXISTS (SELECT 1 FROM qlcv.users WHERE id = OLD.created_by)) THEN
                RAISE EXCEPTION 'Không được thay đổi người tạo.' USING ERRCODE = '23514';
            END IF;
        ELSIF TG_TABLE_NAME = 'attachments' THEN
            IF NEW.uploaded_by IS DISTINCT FROM OLD.uploaded_by
               AND (NEW.uploaded_by IS NOT NULL
                    OR EXISTS (SELECT 1 FROM qlcv.users WHERE id = OLD.uploaded_by)) THEN
                RAISE EXCEPTION 'Không được thay đổi người tải lên.' USING ERRCODE = '23514';
            END IF;
        END IF;
        IF TG_TABLE_NAME IN ('departments', 'users', 'projects', 'tasks') THEN
            NEW.updated_at := clock_timestamp();
        END IF;
    END IF;

    IF TG_OP <> 'INSERT' THEN
        v_old := to_jsonb(OLD) - ARRAY['exclusive_role', 'assignee_role'];
    END IF;
    IF TG_OP <> 'DELETE' THEN
        v_new := to_jsonb(NEW) - ARRAY['exclusive_role', 'assignee_role'];
    END IF;
    v_row := coalesce(v_new, v_old);
    v_action := CASE TG_OP WHEN 'INSERT' THEN 'create'
                          WHEN 'DELETE' THEN 'delete' ELSE 'update' END;

    IF TG_TABLE_NAME IN ('project_members', 'task_members') THEN
        v_key := CASE WHEN TG_TABLE_NAME = 'project_members'
            THEN jsonb_build_object('project_id', v_row->'project_id', 'user_id', v_row->'user_id')
            ELSE jsonb_build_object('task_id', v_row->'task_id', 'user_id', v_row->'user_id') END;
        v_name := 'Thành viên #' || (v_row->>'user_id');
        v_action := CASE TG_OP WHEN 'INSERT' THEN 'add_member'
                              WHEN 'DELETE' THEN 'remove_member' ELSE 'update' END;
    ELSE
        v_key := jsonb_build_object('id', v_row->'id');
        v_name := coalesce(v_row->>'name', v_row->>'full_name', v_row->>'original_filename');
    END IF;

    IF TG_TABLE_NAME = 'projects' THEN
        v_project_id := (v_row->>'id')::bigint;
    ELSE
        v_project_id := (v_row->>'project_id')::bigint;
    END IF;
    IF TG_TABLE_NAME = 'tasks' THEN
        v_task_id := (v_row->>'id')::bigint;
        IF TG_OP = 'UPDATE' AND OLD.progress IS DISTINCT FROM NEW.progress THEN
            v_action := 'update_progress';
        END IF;
    ELSE
        v_task_id := (v_row->>'task_id')::bigint;
    END IF;
    IF v_task_id IS NOT NULL AND v_project_id IS NULL THEN
        SELECT project_id INTO v_project_id FROM qlcv.tasks WHERE id = v_task_id;
        -- Khi xóa dây chuyền, công việc có thể đã bị xóa; lấy dự án từ bản ghi xóa công việc.
        IF v_project_id IS NULL THEN
            SELECT a.project_id INTO v_project_id FROM qlcv.audit_logs a
            WHERE a.entity_type = 'tasks' AND a.task_id = v_task_id
            ORDER BY a.id DESC LIMIT 1;
        END IF;
    END IF;

    IF TG_TABLE_NAME = 'attachments' THEN
        v_action := CASE TG_OP WHEN 'INSERT' THEN 'upload_file'
                              WHEN 'DELETE' THEN 'delete_file' ELSE 'update' END;
    ELSIF TG_TABLE_NAME = 'users' THEN
        IF TG_OP = 'UPDATE' AND OLD.role IS DISTINCT FROM NEW.role THEN
            v_action := 'change_role';
        END IF;
        -- Không đưa mật khẩu hoặc giá trị băm vào lịch sử.
        v_old := v_old - 'password_hash';
        v_new := v_new - 'password_hash';
        IF TG_OP = 'UPDATE' THEN
            v_new := v_new || jsonb_build_object('password_changed', OLD.password_hash IS DISTINCT FROM NEW.password_hash);
        END IF;
    END IF;

    INSERT INTO qlcv.audit_logs(
        actor_id, actor_username, actor_full_name, actor_role, action,
        entity_type, entity_key, entity_name, project_id, task_id, old_data, new_data
    ) VALUES (
        (v_actor->>'id')::bigint, v_actor->>'username', v_actor->>'full_name',
        (v_actor->>'role')::qlcv.app_role, v_action,
        TG_TABLE_NAME, v_key, v_name, v_project_id, v_task_id, v_old, v_new
    );
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION qlcv.reject_history_change_or_truncate() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, qlcv AS $$
BEGIN
    RAISE EXCEPTION 'Không được sửa/xóa lịch sử hoặc TRUNCATE dữ liệu nghiệp vụ.'
        USING ERRCODE = '23514';
END;
$$;

-- Cài trigger sau dữ liệu khởi tạo: lịch sử ban đầu rỗng, chỉ ghi thay đổi khi vận hành.
DO $$
DECLARE v_table text;
BEGIN
    FOREACH v_table IN ARRAY ARRAY[
        'departments', 'users', 'projects', 'project_members',
        'tasks', 'task_members', 'attachments'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER audit_change BEFORE INSERT OR UPDATE OR DELETE ON qlcv.%I FOR EACH ROW EXECUTE FUNCTION qlcv.audit_change()',
            v_table
        );
        EXECUTE format(
            'CREATE TRIGGER reject_truncate BEFORE TRUNCATE ON qlcv.%I FOR EACH STATEMENT EXECUTE FUNCTION qlcv.reject_history_change_or_truncate()',
            v_table
        );
    END LOOP;
END;
$$;
CREATE TRIGGER audit_logs_immutable BEFORE UPDATE OR DELETE ON qlcv.audit_logs
FOR EACH ROW EXECUTE FUNCTION qlcv.reject_history_change_or_truncate();
CREATE TRIGGER audit_logs_no_truncate BEFORE TRUNCATE ON qlcv.audit_logs
FOR EACH STATEMENT EXECUTE FUNCTION qlcv.reject_history_change_or_truncate();

-- 100 * SUM(tiến độ) / (100 * số việc) = AVG(tiến độ), không lưu bản sao tiến độ.
CREATE VIEW qlcv.project_progress AS
SELECT p.id AS project_id, p.name, count(t.id) AS task_count,
       coalesce(avg(t.progress), 0::numeric) AS progress
FROM qlcv.projects p LEFT JOIN qlcv.tasks t ON t.project_id = p.id
GROUP BY p.id, p.name;
COMMENT ON VIEW qlcv.project_progress IS
    'Tiến độ từ công việc hiện có; dự án chưa có việc là 0%. Backend chỉ trả tên và tiến độ cho người không có quyền chi tiết.';

CREATE VIEW qlcv.dashboard_summary AS
WITH counts AS (
    SELECT count(*) AS total_tasks,
           count(*) FILTER (WHERE progress = 0) AS not_started_tasks,
           count(*) FILTER (WHERE progress > 0 AND progress < 100) AS in_progress_tasks,
           count(*) FILTER (WHERE progress = 100) AS completed_tasks
    FROM qlcv.tasks
)
SELECT (SELECT count(*) FROM qlcv.projects) AS total_projects, c.*,
       100.0 * not_started_tasks / nullif(total_tasks, 0) AS not_started_percent,
       100.0 * in_progress_tasks / nullif(total_tasks, 0) AS in_progress_percent,
       100.0 * completed_tasks / nullif(total_tasks, 0) AS completed_percent
FROM counts c;
COMMENT ON VIEW qlcv.dashboard_summary IS
    'Chỉ cấp Dashboard cho Admin/Giám đốc ở backend; tỷ lệ NULL khi chưa có công việc để hiển thị Chưa có dữ liệu.';

-- Không tự tạo PostgreSQL login/role. Backend không được cấp quyền sửa lịch sử.
REVOKE ALL ON ALL TABLES IN SCHEMA qlcv FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA qlcv FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA qlcv FROM PUBLIC;

-- Kiểm tra ngay mọi ràng buộc hoãn trước khi kết thúc import.
SET CONSTRAINTS ALL IMMEDIATE;
COMMIT;
