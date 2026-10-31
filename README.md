# Quản lý công việc nội bộ

Ứng dụng Python, Flask, SQLAlchemy Core, psycopg, Jinja2, Bootstrap và Chart.js theo 42 yêu cầu nghiệp vụ. Toàn bộ dữ liệu nghiệp vụ dùng schema PostgreSQL `qlcv` có sẵn; ánh xạ bảng/view bằng phản chiếu schema. Không dùng `create_all()`, migration tự sinh hoặc import SQL khi khởi động.

## Chạy trên Windows PowerShell

Mở PowerShell tại thư mục dự án. Nếu đã có `.venv` được cài ở máy này:

```powershell
& .\.venv\Scripts\python.exe manage.py check-db
& .\.venv\Scripts\python.exe app.py
```

Mở [http://127.0.0.1:5000](http://127.0.0.1:5000). Ứng dụng dùng Waitress và chỉ lắng nghe trên máy hiện tại. Dừng bằng `Ctrl+C`.

Trên máy mới, cài Python 3.12 trở lên rồi tạo môi trường ảo và cài thư viện:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Các lệnh gọi trực tiếp `.venv\Scripts\python.exe` ở trên đã dùng môi trường ảo, dù dấu nhắc PowerShell chưa hiện `(.venv)`.

Nếu muốn kích hoạt môi trường ảo cho cả phiên PowerShell và dùng lệnh `python`:

```powershell
. .\.venv\Scripts\Activate.ps1
python -c "import sys; print(sys.executable)"
python app.py
```

Đường dẫn in ra phải kết thúc bằng `.venv\Scripts\python.exe`. Khi dùng xong, chạy `deactivate` để thoát môi trường ảo. Nếu máy có chính sách chặn script PowerShell, dùng cách gọi trực tiếp `.venv\Scripts\python.exe` ở trên; không cần thay đổi Execution Policy.

Bootstrap và Chart.js đã lưu trong `qlcv/static/vendor`, trình duyệt không cần kết nối CDN. `requirements-lock.txt` ghi phiên bản đã dùng để kiểm tra; có thể cài từ tệp này để tái lập đúng môi trường.

## Cấu hình .env và cơ sở dữ liệu

Giữ nguyên `.env` có sẵn. Trên máy mới, sao chép `.env.example` sang `.env`, điền thông tin PostgreSQL do người quản trị cung cấp. Ứng dụng đọc `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGSSLMODE`, `PGCONNECT_TIMEOUT`, `PGAPPNAME`; biến môi trường hệ điều hành được ưu tiên nếu đã đặt.

Không đưa `.env`, môi trường ảo, `instance/`, mật khẩu hay tệp người dùng lên Git. Khóa ký phiên được lấy từ `SECRET_KEY` nếu có, nếu thiếu tự tạo một lần trong `instance/secret_key` để giữ phiên ổn định khi khởi động lại. Triển khai qua HTTPS đặt `SESSION_COOKIE_SECURE=1`; cấu hình reverse proxy/HTTPS theo môi trường của đơn vị. Không bật chế độ debug trên máy dùng chung.

`check-db` chỉ đọc để xác nhận kết nối, schema và số bản ghi. Nếu đã có `qlcv`, dùng trực tiếp. Nếu chưa có schema, chỉ dùng lệnh sau trên **cơ sở dữ liệu đích rỗng đã được tạo trước**:

```powershell
& .\.venv\Scripts\python.exe manage.py init-db
```

Công cụ kiểm tra bảng, view, sequence, hàm, kiểu dữ liệu, schema và extension do người dùng tạo trước khi import. Cơ sở dữ liệu không rỗng bị từ chối; đã có `qlcv` thì không import lại. Bản `database/init.sql` được sao chép nguyên vẹn từ đầu vào; SHA-256: `9AEE03B147D9933BCE6FFB8EA1DB82A06B549B9BC36D48D5137D4B5ED9862628`.

Tài khoản PostgreSQL của ứng dụng cần quyền đọc/ghi các bảng nghiệp vụ, dùng sequence, đọc hai view và thực thi `qlcv.set_actor`. Tài khoản không cần quyền sửa/xóa `audit_logs`; lịch sử do hàm trigger `SECURITY DEFINER` ghi. Nếu `.env` đang sử dụng chủ sở hữu schema, trigger vẫn chặn sửa/xóa lịch sử. Khi vận hành, đơn vị có thể cấp tài khoản kết nối riêng với quyền tối thiểu, giữ nguyên schema.

## Đăng nhập và sử dụng

Đăng nhập bằng tên tài khoản và **mật khẩu đã được đơn vị cấp**. Không tự đăng ký, không có mật khẩu mặc định do ứng dụng đặt. Các bcrypt trong SQL được giữ nguyên và kiểm tra bằng bcrypt; không suy đoán hoặc đặt lại mật khẩu khởi tạo. Admin có thể tạo tài khoản và nhập mật khẩu mới cho tài khoản do mình quản lý.

| Vai trò | Chức năng chính |
| --- | --- |
| Admin | Quản lý tài khoản, toàn bộ dự án/công việc/tài liệu, Dashboard và lịch sử; vẫn chịu điều kiện xóa và người phụ trách |
| Giám đốc | Dashboard, xem tất cả dự án/công việc/tài liệu; quyền xem không tự cấp quyền quản trị hay ghi dữ liệu |
| Trưởng bộ phận | Tạo dự án/công việc, thêm Nhân viên, sửa đối tượng do mình tạo; cập nhật tiến độ công việc được truy cập |
| Nhân viên | Xem chi tiết đối tượng mình tham gia, tài liệu tương ứng; cập nhật tiến độ và tải tài liệu riêng khi là người phụ trách |

1. Admin hoặc TBP tạo dự án. TBP tạo dự án được tự thêm vào dự án.
2. Mở **Thêm thành viên**, chọn dự án để thêm Nhân viên; không giới hạn theo bộ phận.
3. Tạo công việc, chọn dự án và Nhân viên đã thuộc dự án làm người phụ trách. Người phụ trách tự được thêm vào công việc. TBP tạo công việc cũng tự được thêm vào công việc; nếu chưa thuộc dự án, hệ thống thêm TBP vào dự án trong cùng giao dịch để đáp ứng khóa ngoại.
4. Quản lý thành viên công việc để thêm người từ dự án. Muốn chuyển người phụ trách, thêm người mới vào công việc trước, sau đó vào **Sửa công việc** chọn người mới.
5. Người có quyền cập nhật tiến độ kéo thanh 0–100% và bấm **Lưu tiến độ**. Tiến độ dự án lấy trực tiếp từ view, là trung bình tiến độ các công việc; chưa có việc là 0%.
6. Tải lên tài liệu tại dự án hoặc công việc. Tài liệu riêng của công việc chỉ do Admin hoặc Nhân viên phụ trách tải lên; mọi người được xem chi tiết công việc vẫn được tải xuống tài liệu đó.
7. Muốn xóa tài khoản đang phụ trách công việc, chuyển người phụ trách trước. Muốn thay Admin/Giám đốc, vào **Tài khoản → Chuyển vai trò**; người giữ vai trò và người nhận hoán đổi vai trò/bộ phận trong một giao dịch. Sau đó mới có thể xóa người cũ nếu đủ điều kiện.

Quyền tải lên tài liệu chung dựa vào tư cách thành viên hoặc toàn quyền Admin; nếu Giám đốc được Admin thêm làm thành viên thì quyền thành viên được áp dụng theo yêu cầu 32–33. Admin có thể quản lý thành viên mọi vai trò; TBP thêm/gỡ Nhân viên. Việc gỡ thành viên không được làm mất thành viên bắt buộc của người phụ trách. Gỡ thành viên dự án cũng gỡ người đó khỏi các công việc trong dự án.

TBP có quyền tạo công việc và thêm Nhân viên không phụ thuộc bộ phận/người tạo đối tượng. Trình chọn chỉ cung cấp tên đối tượng cần thao tác; khi chưa có quyền chi tiết, không hiển thị mô tả hoặc danh sách thành viên hiện tại. Quyền sửa thông tin vẫn theo người tạo; quyền xem chi tiết vẫn theo thành viên. Thành viên dự án không mặc nhiên xem được chi tiết mọi công việc.

## Giao dịch, bảo mật và tệp

Mỗi thao tác ghi kiểm tra lại tài khoản, vai trò và thành viên từ cơ sở dữ liệu. Phiên chỉ mang định danh tài khoản và dấu xác thực; thay mật khẩu vô hiệu hóa phiên cũ, xóa tài khoản hoặc đổi vai trò có tác dụng ở yêu cầu tiếp theo. Các yêu cầu ghi trong ứng dụng dùng khóa giao dịch chung để tránh kiểm tra quyền/thành viên đồng thời bị lệch; ràng buộc SQL vẫn là lớp bảo vệ dữ liệu cuối cùng.

Backend gọi `qlcv.set_actor(id)` từ phiên đã xác thực sau khi kiểm tra quyền, trên chính kết nối và giao dịch ghi. Trigger ghi lịch sử, không có mã ghi trùng lịch sử. Chỉ xem dữ liệu không tạo lịch sử. Lịch sử dự án không trả các thao tác chứa nội dung công việc bị hạn chế; lịch sử riêng của công việc theo quyền xem công việc. Admin xem được lịch sử toàn bộ, kể cả đối tượng đã xóa.

Biểu mẫu có CSRF, phiên HttpOnly/SameSite, giới hạn thử đăng nhập, truy vấn tham số hóa, HTML tự escape và header bảo mật. Không nhận vai trò/người thực hiện/người tạo từ trình duyệt để xác định quyền. Tệp tối đa 25 MB được lưu bằng khóa ngẫu nhiên trong `instance/uploads/`, không nằm trong static; tên gốc chỉ để hiển thị/tải xuống. Mỗi lần tải xuống hoặc xóa đều kiểm tra quyền lại. Tệp được gửi dưới dạng đính kèm để tránh chạy nội dung HTML/SVG do người dùng cung cấp.

Khi xóa dữ liệu, chỉ xóa tệp vật lý sau khi giao dịch đã thành công. Upload thất bại chắc chắn sẽ dọn tệp mới; nếu mất kết nối đúng lúc COMMIT và chưa rõ kết quả, giữ tệp để tránh mất dữ liệu. Nếu tiến trình bị dừng giữa chừng, có thể còn tệp mồ côi. Công cụ dưới đây chỉ xử lý tệp không được cơ sở dữ liệu tham chiếu và cũ hơn 24 giờ:

```powershell
# Chỉ xem danh sách
& .\.venv\Scripts\python.exe manage.py clean-files
# Thực sự dọn các tệp mồ côi đã được xác định
& .\.venv\Scripts\python.exe manage.py clean-files --apply
```

Sao lưu PostgreSQL và thư mục `instance/uploads/` cùng đợt để khôi phục nhất quán; giữ lại khóa phiên nếu muốn duy trì phiên khi phục hồi.

## Kiểm thử

Chạy bộ kiểm thử qua công cụ riêng:

```powershell
& .\.venv\Scripts\python.exe scripts/run_tests.py
```

Công cụ cần quyền `CREATEDB` trên PostgreSQL. Nó tạo một CSDL `qlcv_test_<chuỗi ngẫu nhiên>` riêng, nạp nguyên bản SQL, chạy pytest và xóa đúng CSDL do lần chạy này tạo. Bộ kiểm thử làm mới schema và đổi bcrypt **chỉ trong CSDL kiểm thử**. Không chạy pytest ghi trực tiếp vào CSDL `.env`; fixture sẽ từ chối nếu chưa có định danh CSDL kiểm thử hợp lệ.

Công cụ so sánh số lượng và dấu kiểm tra nội dung của toàn bộ 8 bảng đang dùng trước/sau; không xuất dữ liệu, mật khẩu hoặc thông tin kết nối. Kết quả nằm trong `test-results/pytest.xml` và `test-results/verification.json`. Bộ kiểm thử tập trung vào bốn vai trò, URL trực tiếp, dữ liệu bị hạn chế, CSRF, đổi vai trò, xóa tài khoản, thành viên, người phụ trách, tiến độ, tệp, cascade và lịch sử bất biến.

Để xem giao diện bằng dữ liệu kiểm thử sau khi tất cả kiểm thử thành công:

```powershell
& .\.venv\Scripts\python.exe scripts/run_tests.py --serve-preview
```

Bản xem thử dùng cổng `5001`, tài khoản kiểm thử `admin`, `giamdoc`, `tbp_phanmem`, `phanmem_nv01` cùng mật khẩu kiểm thử `KiemThu2026!`. Các mật khẩu này **chỉ có trong CSDL kiểm thử tạm thời**, không dùng cho dữ liệu thật. Dừng bằng `Ctrl+C` để công cụ dọn CSDL kiểm thử. Ứng dụng chính vẫn chạy bằng `.env` ở cổng `5000`.

## Mã nguồn và đối chiếu

- `qlcv/config.py`: cấu hình môi trường, phiên và nơi lưu tệp.
- `qlcv/db.py`: SQLAlchemy, phản chiếu schema, kết nối và giao dịch.
- `qlcv/permissions.py`: các quy tắc quyền dùng ở backend.
- `qlcv/routes.py`: đăng nhập và các luồng nghiệp vụ.
- `qlcv/files.py`: lưu và dọn tệp an toàn.
- `qlcv/templates/`, `qlcv/static/`: giao diện tiếng Việt, responsive.
- `database/init.sql`: bản SQL đầu vào nguyên vẹn.
- `tests/`, `scripts/run_tests.py`: kiểm thử tích hợp PostgreSQL riêng.
- [Đối chiếu 42 yêu cầu](docs/doi-chieu-42-yeu-cau.md).
- [Kết quả kiểm tra thực tế](docs/kiem-tra-thuc-te.md).
