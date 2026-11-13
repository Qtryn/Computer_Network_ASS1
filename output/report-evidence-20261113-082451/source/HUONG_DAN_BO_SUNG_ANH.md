# Hướng dẫn hoàn thiện report Assignment 1

Bản PDF này **cố ý còn 6 khung vàng `EVIDENCE TO INSERT`**. Đây là vị trí để nhóm chèn ảnh bằng chứng THẬT từ phiên bản `main` sau khi merge. Không nên nộp PDF khi còn các khung này.

## Chèn ảnh trên Overleaf

1. Upload toàn bộ ZIP này lên Overleaf và dùng pdfLaTeX cho `main.tex`.
2. Trong thư mục `evidence/`, upload ảnh PNG có **đúng tên** ở bảng dưới.
3. Recompile; khung vàng tương ứng sẽ **tự động được thay bằng ảnh**. Không cần sửa LaTeX.
4. Nếu ảnh quá nhỏ, crop chỉ lấy phần giao diện/terminal cần chứng minh. Không dùng ảnh từ branch UI cũ để thay cho bằng chứng về bản main mới.

| Tên file | Cần chụp gì |
|---|---|
| `01_https_login_roster.png` | Trình duyệt Chrome HTTPS: đăng nhập account-mode và online users |
| `02_chat_file_verification.png` | Chat private/broadcast và tiến trình/biên nhận file SHA-256 (có thể ghép hai ảnh thật) |
| `03_pending_before_restart.png` | Tin nhắn đang PENDING khi server mất kết nối |
| `04_delivered_after_relogin.png` | Đăng nhập lại sau khi server chạy lại, các tin cũ DELIVERED một lần, đúng thứ tự |
| `05_wireshark_udp_retransmission.png` | Wireshark mở `final-loopback.pcapng`: DATA 109, 120 và ACK 121; TCP/UDP 19100/19101 |
| `06_tests_and_concurrency.png` | Terminal thực chạy 65/65 tests và load 20 clients PASS |

Không để lộ mật khẩu, token, AES key hoặc private key khi chụp. Nếu chưa chụp được, giữ khung và đừng đánh dấu đã có bằng chứng.

## Các ô vàng ở cuối báo cáo

- **LECTURER CONFIRMATION:** BBR/CUBIC chưa được triển khai; thầy có yêu cầu bắt buộc không?
- **OFFLINE REQUIREMENT:** Tin chờ hiện chỉ trong RAM; tắt hẳn client thì mất. Thầy có yêu cầu lưu qua khởi động lại không?
- **ADMINISTRATIVE CHECK:** Xác nhận quy định nhóm 5 người và deadline LMS.
- **EVIDENCE TO ATTACH:** Thay các khung bằng ảnh thật.
- **OPTIONAL VERIFICATION:** Chưa test hai máy LAN độc lập; đề cho phép localhost nhưng có thể bổ sung nếu cần.

Chỉ xóa lời nhắc sau khi đã thực hiện/xác nhận. Báo cáo tiếng Anh vẫn mô tả đúng những tính năng đã được code và kiểm thử trên localhost, không tự nhận BBR/CUBIC hoặc persistent outbox.
