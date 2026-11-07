# Đề xuất protocol và triển khai TV1

Bản này mô tả nhánh TV1 để nhóm review. Hợp đồng UDP của nhóm nằm trong [đặc tả hiện tại](protocol.md).

| Phương án transport | Ưu điểm | Chi phí và mức phù hợp |
|---|---|---|
| TCP điều khiển, UDP tin cậy truyền chat/file | TCP phục vụ handshake, đăng nhập và heartbeat. UDP giữ được phần ACK, truyền lại và stream mà nhóm đã làm. | Phải liên kết token TCP với địa chỉ IP và cổng UDP. Phù hợp nhất với repo hiện tại và giữ được cả hai phần cần trình bày trong rubric. **Phương án 1. TV1 xác nhận chọn ngày 2026-11-07.** |
| Toàn bộ trên TCP | Client quản lý một kênh. TCP đảm nhận truyền lại và thứ tự. | Phải đổi đường truyền chat/file và làm rõ với giảng viên cách đáp ứng phần UDP tin cậy. |
| Toàn bộ trên UDP tin cậy | Điều khiển và dữ liệu dùng chung cơ chế đóng gói và truyền lại. | Cần tự thiết kế vòng đời kết nối và cơ chế đăng nhập tin cậy trên UDP. Rubric hiện có mốc handshake TCP, nên cần giảng viên xác nhận nếu chọn hướng này. |

Với thông điệp điều khiển, JSON UTF-8 kết thúc bằng `LF` cho phép đọc log trực tiếp và giữ tương thích với client nhóm. Tiền tố độ dài phù hợp khi cần đóng gói dữ liệu nhị phân trên TCP, nhưng hai đầu phải đổi parser. TV1 dùng JSON theo dòng, tối đa 4.096 byte mỗi dòng trước `LF`. Bên nhận xử lý lần lượt các dòng hoàn chỉnh và giữ phần dở cho lần đọc kế tiếp. [RFC 9293 về luồng TCP](https://www.rfc-editor.org/rfc/rfc9293.html#section-2.2) · [RFC 8259 về UTF-8](https://www.rfc-editor.org/rfc/rfc8259.html#section-8.1)

Server tiếp tục dùng một luồng cho mỗi kết nối và giới hạn 64 kết nối TCP. Cách này tái sử dụng socket blocking hiện có và đủ chỗ cho bài kiểm 20 client. Một vòng lặp async có thể phù hợp ở tải lớn hơn, nhưng cần đổi cách quản lý socket và trạng thái. Luồng cập nhật danh sách online chạy riêng để việc chờ ACK UDP không chặn phản hồi đăng nhập.

Registry giữ **một phiên online cho mỗi username** theo hợp đồng định tuyến hiện tại. Nhiều phiên cùng username sẽ cần quyết định chat/file được gửi đến phiên nào. Token gắn với username, IP và cổng UDP. Phiên có hiệu lực mặc định 3.600 giây từ lúc đăng nhập thành công. Heartbeat duy trì kết nối idle trong giới hạn 12 giây và thời hạn phiên vẫn tính từ lần xác thực ban đầu.

## Chế độ chạy và thông điệp TCP

Chế độ demo mặc định tiếp nhận `LOGIN` đầu tiên theo hợp đồng cũ. Client mới có thể gửi `HELLO(version=1)` trước `LOGIN`. Chế độ có mật khẩu yêu cầu TLS và `HELLO`. Nó dùng PBKDF2-HMAC-SHA256 với salt riêng và 600.000 vòng, cùng bộ đếm theo tài khoản. Mặc định sai ba lần sẽ khóa 60 giây. Các tham số này có thể chỉnh khi chạy. [Tài liệu TLS của Python](https://docs.python.org/3/library/ssl.html) · [OWASP về lưu trữ mật khẩu](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#pbkdf2)

| Thông điệp | Trường hoặc hành vi |
|---|---|
| `HELLO` → `HELLO_OK` | Client gửi `version: 1`. Server xác nhận phiên bản ứng dụng. |
| `LOGIN` → `LOGIN_OK` | Client gửi `username`, `udp_port`, và `password` trong chế độ TLS. Phản hồi giữ `token`, `users`, `version` của danh sách online, `udp_port` và thêm `expires_in_seconds`. |
| `LOGIN_FAIL` / `LOGIN_LOCKED` | Trả `remaining_attempts` hoặc `retry_after_seconds`. Kết nối lại vẫn dùng bộ đếm của tài khoản. |
| `GET_USERS` → `USERS` | Phiên hợp lệ lấy danh sách `users` và phiên bản danh sách qua TCP. Đường cập nhật UDP của client hiện tại vẫn được hỗ trợ. |
| `AUTH_REQUIRED` | Kết nối đã qua `HELLO` cần `LOGIN` trước khi thực hiện lệnh cần phiên. Sau khi hết hạn có thể đăng nhập lại trên cùng kết nối. Client demo dùng `LOGIN` trực tiếp sẽ bị đóng kết nối khi phiên hết hạn. |
| `PROTOCOL_ERROR` | `HELLO_REQUIRED` cho sai thứ tự trước handshake. `UNSUPPORTED_VERSION` và `INVALID_MESSAGE` đóng kết nối sau phản hồi nếu còn gửi được. |
| `PING` / `LOGOUT` | `PING` duy trì kết nối của phiên hợp lệ. `LOGOUT` kết thúc kết nối và bỏ phiên khỏi danh sách online. |

## Chạy thử

Từ thư mục repo, dùng virtual environment và cài dependency theo [README](../README.md). Để kiểm riêng mục 2–4 với chứng chỉ thử tạo tạm, chạy:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_server_control -v
```

Để chạy chế độ có mật khẩu bằng chứng chỉ PEM đã cấp cho server, tạo tài khoản local và dùng các cờ dưới đây. Client thử cần tin cậy chứng chỉ hoặc CA đã cấp và xác minh đúng tên server. Tạo khóa UDP theo hướng dẫn trong README trước khi chạy server.

```powershell
.\.venv\Scripts\python.exe -m app.server.auth alice
.\.venv\Scripts\python.exe -m app.run_server --accounts config/local_accounts.json --tls-cert config/local_tls/server.pem --tls-key config/local_tls/server.key
```

Nhóm có thể tiếp tục chạy server và client demo bằng lệnh cũ trong README. Việc nối chế độ TLS/mật khẩu vào client và UI của nhóm là một bước tích hợp riêng.
