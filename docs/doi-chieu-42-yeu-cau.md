# Đối chiếu 42 yêu cầu nghiệp vụ

Đặc tả Word là căn cứ nghiệp vụ; `database/init.sql` là căn cứ cấu trúc. Không phát hiện mâu thuẫn cần sửa schema. Khi TBP tạo công việc trong dự án chưa tham gia, bổ sung TBP vào dự án trong cùng giao dịch để bảo đảm thành viên công việc phải thuộc dự án.

| STT | Phần thực hiện | Kiểm chứng |
| --- | --- | --- |
| 1 | Bốn vai trò, duy nhất một Giám đốc | Enum, UNIQUE hoãn và trigger SQL; kiểm thử chuyển vai trò |
| 2 | Admin toàn quyền, vẫn chịu điều kiện xóa | Kiểm thử điều kiện xóa, người phụ trách, tài liệu |
| 3 | Vai trò có sẵn, không cấu hình quyền tùy chỉnh | Enum, biểu mẫu và kiểm tra giá trị backend |
| 4 | Đăng nhập bcrypt | Kiểm thử đăng nhập bốn vai trò và tài khoản bcrypt mới |
| 5 | Đăng xuất POST có CSRF | Kiểm thử đăng xuất và truy cập sau đăng xuất |
| 6 | Không tự đăng ký | Chỉ Admin có endpoint tạo tài khoản |
| 7 | Danh sách tài khoản cho Admin | Kiểm thử quyền bốn vai trò và render danh sách |
| 8 | Chi tiết tài khoản cho Admin | Kiểm thử trang chi tiết, không trả password_hash |
| 9 | Admin tạo tài khoản | Kiểm thử tạo bcrypt, bộ phận và vai trò |
| 10 | Admin sửa thông tin tài khoản | Kiểm thử thay mật khẩu, thông tin và vai trò |
| 11 | Xóa tài khoản đủ điều kiện | Kiểm thử chặn xóa Admin/Giám đốc/người đang phụ trách |
| 12 | Giữ đối tượng, tài liệu và danh tính lịch sử khi xóa người | Kiểm thử xóa người tạo/tải lên, FK SET NULL, tệp còn tồn tại |
| 13 | Đổi vai trò; hoán đổi vai trò độc quyền nguyên tử | Kiểm thử chuyển Giám đốc/Admin, quyền phiên hiện có cập nhật |
| 14 | Tên, nội dung, thành viên và tiến độ dự án | Trang chi tiết dự án và biểu mẫu |
| 15 | Tiến độ dự án theo công việc hiện có | View project_progress; kiểm thử thêm/xóa/cập nhật và dự án rỗng |
| 16 | Danh sách dự án hạn chế chỉ tên, phần trăm | Kiểm thử HTML không chứa mô tả/đường dẫn chi tiết trái quyền |
| 17 | Quyền mở chi tiết dự án | Kiểm thử URL trực tiếp với thành viên, người ngoài và Admin/Giám đốc |
| 18 | Admin/TBP tạo dự án, tự thêm TBP | Kiểm thử người tạo và thành viên mặc định |
| 19 | Admin/TBP thêm Nhân viên dự án | Kiểm thử thành viên khác bộ phận, chặn vai trò khác thao tác |
| 20 | Admin sửa mọi dự án, TBP sửa dự án do mình tạo | Kiểm thử TBP tạo và TBP khác |
| 21 | Người tạo/Admin xóa dự án chưa có việc | Kiểm thử chặn dự án có việc và xóa dự án rỗng |
| 22 | Công việc thuộc dự án và có đủ thông tin | Biểu mẫu, chi tiết, thành viên, người phụ trách, tài liệu |
| 23 | Danh sách công việc chỉ tên và phần trăm khi bị hạn chế | Kiểm thử người thuộc dự án nhưng chưa thuộc công việc |
| 24 | Chi tiết công việc theo thành viên riêng | Kiểm thử URL trực tiếp, cả Admin/Giám đốc không là thành viên |
| 25 | Admin/TBP tạo công việc, tự thêm TBP | Kiểm thử tạo và khóa ngoại hoãn trong cùng giao dịch |
| 26 | Thành viên công việc thuộc dự án, người phụ trách là Nhân viên thành viên | Kiểm thử thêm người ngoài dự án, chuyển phụ trách và gỡ người |
| 27 | Admin sửa mọi công việc, TBP sửa việc do mình tạo | Kiểm thử TBP khác, Nhân viên, Giám đốc bị chặn |
| 28 | Chỉ Admin xóa việc tiến độ 0% | Kiểm thử vai trò và tiến độ khác 0 |
| 29 | Cascade thành viên/tài liệu, giữ lịch sử | Kiểm thử xóa việc, bản ghi tài liệu, tệp vật lý và log |
| 30 | Thanh kéo, quyền cập nhật tiến độ | Ma trận Admin/Giám đốc/TBP có và không truy cập/Nhân viên phụ trách/người khác |
| 31 | Ba loại tài liệu | Ba vùng hiển thị và enum kiểm tra kind ở backend/SQL |
| 32 | Upload tài liệu chung dự án theo thành viên/Admin | Kiểm thử upload nhiều vai trò |
| 33 | Upload tài liệu chung công việc theo thành viên/Admin | Kiểm thử thành viên dự án chưa thuộc công việc |
| 34 | Upload tài liệu riêng chỉ Admin/người phụ trách | Kiểm thử TBP và Giám đốc bị chặn |
| 35 | Cả hai loại tài liệu công việc theo quyền chi tiết công việc | Kiểm thử tài liệu riêng được TBP thành viên xem, người ngoài bị chặn |
| 36 | Tải xuống theo quyền xem tài liệu | Kiểm thử URL tải xuống, HTTP attachment và nội dung tệp |
| 37 | Admin/người tải lên còn quyền truy cập được xóa | Kiểm thử người khác và người tải lên bị gỡ khỏi công việc |
| 38 | Phân quyền backend ở URL và POST trực tiếp | Kiểm thử truy cập/ghi trực tiếp bốn vai trò |
| 39 | Trigger ghi đầy đủ thay đổi, giữ actor, lịch sử bất biến | Kiểm thử actor giả từ browser, không ghi khi xem, chặn sửa/xóa lịch sử và thiếu actor |
| 40 | Dashboard chỉ Admin/Giám đốc | Kiểm thử quyền bốn vai trò |
| 41 | Số hiện có, ba trạng thái công việc | View dashboard_summary và kiểm thử thay đổi số sau xóa |
| 42 | Chart.js biểu đồ cột và tròn, tỷ lệ, trạng thái rỗng | Dữ liệu từ hai view, kiểm thử trang rỗng và tổng hợp |

Giao diện chỉ ẩn nút theo quyền để dễ sử dụng; mọi quyết định quyền đều được lặp lại tại backend. Quyền được nạp lại ở mỗi yêu cầu, không lưu vai trò hoặc tư cách thành viên vào cookie.
