# Kiểm tra thực tế

Đã thực hiện ngày 29/10/2026, múi giờ Việt Nam. Kết quả máy thực nằm trong `test-results/`, không chứa thông tin kết nối.

## Kết quả

| Hạng mục | Kết quả thực tế |
| --- | --- |
| Đọc đặc tả | Đã đọc đầy đủ 42 yêu cầu trong Word và toàn bộ SQL |
| Kết nối PostgreSQL | Thành công bằng `.env` hiện có, thao tác kiểm tra chỉ đọc |
| Schema | Đã có `qlcv`, không import lại; đối chiếu cột, kiểu/enum, khóa, chỉ mục, view, hàm và trigger khớp SQL đầu vào |
| Dữ liệu ban đầu | 3 bộ phận, 14 tài khoản: 1 Admin, 1 Giám đốc, 3 TBP, 9 Nhân viên; chưa có dự án/công việc/tài liệu/lịch sử |
| Bộ kiểm thử cuối | **57 passed**, 196,26 giây; CSDL PostgreSQL riêng, tên ngẫu nhiên |
| Toàn vẹn dữ liệu đang dùng | Dấu kiểm tra nội dung và số bản ghi của cả 8 bảng trước/sau kiểm thử giống nhau |
| Phụ thuộc Python | `pip check`: không có phụ thuộc lỗi |
| Cú pháp Python | `compileall`: thành công |
| Chạy ứng dụng | Flask/Waitress khởi động bằng cấu hình thật; `GET /dang-nhap` trả HTTP 200 |
| Trình duyệt | Đăng nhập Admin bằng tài khoản kiểm thử; mở Dashboard, danh sách/chi tiết dự án và công việc thành công |
| Biểu mẫu có CSRF | Lưu tiến độ công việc từ 65% lên 70% trên trình duyệt thành công; tiến độ dự án cập nhật 70%, lịch sử ghi đúng Admin thực hiện |
| Biểu đồ | Biểu đồ cột và tròn thực tế hiển thị đúng dữ liệu; ba nhóm 1/3 tương ứng 33,3%; console không có lỗi/cảnh báo JavaScript |
| Responsive | Kiểm tra kích thước máy tính 1366 px và điện thoại 390 px; menu thu gọn mở được, không tràn ngang Dashboard |
| SQL bàn giao | Bản sao nguyên vẹn, SHA-256 ghi trong README |

Các kiểm thử bao gồm phân quyền bốn vai trò, URL/POST trực tiếp, danh sách bị hạn chế, creator, thành viên mặc định, khóa ngoại hoãn, xóa có điều kiện, đổi/hoán đổi vai trò, thu hồi quyền phiên cũ, thanh tiến độ, ba loại tài liệu, gỡ người tải lên, lỗi upload và hoàn tác tệp, cascade, actor giả, lịch sử bất biến và XSS.

Các lỗi phát hiện trong lượt đầu đã sửa: thời hạn CSRF cần cấu hình bằng số giây; kiểm thử phải tra ID theo username, không giả định thứ tự identity của dữ liệu khởi tạo. Đã chạy lại toàn bộ bộ kiểm thử sau sửa và sau bổ sung trường hợp hoán đổi Admin/Giám đốc.

## Phạm vi và vận hành

Không kiểm thử đăng nhập bằng tài khoản thật vì đầu vào không cung cấp mật khẩu dạng rõ. Không suy đoán hoặc đặt lại các bcrypt khởi tạo. Luồng xác thực được kiểm tra bằng các tài khoản/bcrypt chỉ tạo hoặc thay đổi trong CSDL kiểm thử riêng.

Ảnh giao diện dùng dữ liệu minh họa **trong CSDL kiểm thử**, không phải dữ liệu đang dùng:

- [Dashboard máy tính](anh-kiem-tra/dashboard-may-tinh.png).
- [Dashboard điện thoại](anh-kiem-tra/dashboard-dien-thoai.png).

Các tiến trình phục vụ kiểm tra được dừng sau khi kiểm tra. Chạy lại ứng dụng chính bằng lệnh trong README. Không có vấn đề nghiệp vụ còn bị chặn ở thời điểm bàn giao.
