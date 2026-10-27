# TikTok Streak CLI

TikTok Streak CLI là công cụ dòng lệnh tự động gửi tin nhắn trực tiếp trên TikTok hàng ngày để duy trì chuỗi nhắn tin liên tục (streak) với bạn bè, giúp bạn không bị đứt chuỗi do quên hoặc bận rộn.

---

## Tính năng nổi bật

* **Đăng nhập một lần duy nhất:** Sử dụng Playwright để mở trình duyệt Chromium cho bạn đăng nhập và lưu lại phiên làm việc (cookies/session). Các lần chạy sau sẽ diễn ra hoàn toàn tự động ở chế độ ẩn.
* **Chống gửi lặp trong ngày:** Tự động ghi nhận ngày gửi theo múi giờ Việt Nam (GMT+7). Những bạn bè đã nhận tin nhắn trong ngày hôm nay sẽ được tự động bỏ qua để tránh làm phiền.
* **Chế độ chạy thử nghiệm (Dry-run):** Cho phép kiểm tra và xem trước danh sách người nhận, nội dung tin nhắn sẽ gửi mà không thực sự mở trình duyệt hay gửi tin nhắn.
* **Nội dung tin nhắn linh hoạt:** Hỗ trợ tin nhắn mặc định chung cho toàn bộ danh sách, đồng thời cho phép cài đặt tin nhắn riêng biệt cho từng người bạn.
* **Tự động chạy cùng Windows (Autostart):** Tích hợp script chạy nền trong thư mục Startup của Windows, tự động đợi kết nối mạng sẵn sàng rồi gửi tin nhắn mỗi khi bật máy tính.
* **Thông báo Windows Toast:** Hiển thị thông báo dạng pop-up ở góc phải màn hình Windows khi gửi thành công hoặc khi xảy ra sự cố cần xử lý.

---

## Cấu trúc mã nguồn

Toàn bộ mã nguồn dự án được gom gọn trong thư mục `src/` thành 3 tệp chính:

```
tiktok-streak/
├── src/
│   ├── main.py       # Điểm thực thi CLI (Typer) và tiến trình tự chạy cùng Windows
│   ├── tiktok.py     # Tự động hóa trình duyệt qua Playwright (đăng nhập, lấy userId, gửi tin nhắn)
│   └── storage.py    # Quản lý dữ liệu JSON, tính toán múi giờ Việt Nam và thông báo Windows
├── data/             # Chứa recipients.json, settings.json và tiktok-session.json
├── logs/             # Chứa autostart.log lưu lại lịch sử các lần chạy
├── .gitignore        # Cấu hình bỏ qua môi trường ảo, cache và dữ liệu cục bộ
├── pyproject.toml    # Cấu hình dự án và danh sách thư viện phụ thuộc
└── README.md         # Tài liệu hướng dẫn sử dụng
```

---

## Yêu cầu hệ thống

* **Hệ điều hành:** Windows 10 hoặc Windows 11 (để sử dụng tính năng thông báo Windows Toast và khởi động nền cùng hệ thống).
* **Python:** Phiên bản 3.11 trở lên.

---

## Cài đặt từ đầu

1. Mở PowerShell tại thư mục dự án ví dụ: (`D:\tiktok-streak`).
2. Tạo và kích hoạt môi trường ảo:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Cài đặt dự án và các thư viện phụ thuộc:

   ```powershell
   pip install -e .
   ```
4. Tải nhân trình duyệt Chromium cho Playwright:

   ```powershell
   playwright install chromium
   ```

---

## Hướng dẫn sử dụng

### 1. Đăng nhập TikTok (Bắt buộc thực hiện lần đầu)

Chạy lệnh sau để mở trình duyệt đăng nhập:

```powershell
streak-saver login
```

* Cửa sổ trình duyệt Chromium sẽ xuất hiện trên trang chủ TikTok.
* Hãy đăng nhập vào tài khoản của bạn.
* Sau khi đăng nhập thành công vào trang chủ, quay lại cửa sổ terminal và nhấn phím **Enter**. Phiên đăng nhập sẽ được lưu vào tệp `data/tiktok-session.json` để sử dụng cho mọi lần gửi sau này.

---

### 2. Quản lý danh sách người nhận (`user`)

* **Xem danh sách bạn bè hiện tại:**

  ```powershell
  streak-saver user list
  ```
* **Thêm bạn bè vào danh sách nhận tin:**

  ```powershell
  streak-saver user add <username>
  ```

  *(Hệ thống sẽ tự động quét trang cá nhân để lấy userId tương ứng).*
* **Xóa một người khỏi danh sách:**

  ```powershell
  streak-saver user remove <username>
  ```
* **Cài đặt tin nhắn riêng cho một người:**

  ```powershell
  streak-saver user set-msg <username> "Chào ngày mới"
  ```
* **Xóa tin nhắn riêng (quay về dùng tin nhắn mặc định):**

  ```powershell
  streak-saver user clear-msg <username>
  ```

---

### 3. Gửi tin nhắn duy trì Streak (`send`)

* **Chạy thử nghiệm (Dry-run - không gửi thật, không mở trình duyệt):**

  ```powershell
  streak-saver send --dry-run
  ```
* **Gửi tin nhắn thật cho toàn bộ danh sách:**

  ```powershell
  streak-saver send
  ```

  *(Những bạn bè đã nhận tin nhắn trong ngày hôm nay sẽ được tự động bỏ qua).*
* **Bắt buộc gửi lại (kể cả những người đã gửi hôm nay):**

  ```powershell
  streak-saver send --force
  ```
* **Chỉ gửi cho một người cụ thể:**

  ```powershell
  streak-saver send -u <username>
  ```
* **Gửi với nội dung tin nhắn tùy chọn tạm thời:**

  ```powershell
  streak-saver send -m "Tin nhắn tùy chọn"
  ```

---

### 4. Quản lý cấu hình (`config`)

* **Xem các thiết lập hiện tại:**

  ```powershell
  streak-saver config
  ```
* **Đổi tin nhắn mặc định của toàn hệ thống:**

  ```powershell
  streak-saver config set-msg "<3"
  ```

---

### 5. Tự động chạy khi khởi động Windows (`autostart`)

Công cụ hỗ trợ tự động gửi tin nhắn duy trì streak mỗi ngày khi bạn mở máy tính:

* **Kích hoạt tự động chạy khi bật máy:**

  ```powershell
  streak-saver autostart enable
  ```

  *(Tệp script `.vbs` sẽ được tạo trong thư mục Startup của Windows, tự động chạy ngầm không hiện cửa sổ).*
* **Kiểm tra trạng thái và lịch sử log gần nhất:**

  ```powershell
  streak-saver autostart status
  ```
* **Chạy thử tiến trình khởi động bằng tay:**

  ```powershell
  streak-saver autostart run
  ```
* **Tắt tính năng tự động chạy cùng Windows:**

  ```powershell
  streak-saver autostart disable
  ```

---

## Lưu ý về bảo mật và vận hành

* Tệp `data/tiktok-session.json` chứa cookie và token phiên đăng nhập cá nhân của bạn. Không chia sẻ tệp này cho người khác hoặc đưa lên kho lưu trữ mã nguồn công khai.
* Khoảng thời gian giãn cách giữa các tin nhắn được thiết lập có độ trễ hợp lý nhằm mô phỏng hành vi tự nhiên của con người, hạn chế nguy cơ bị TikTok giới hạn tính năng nhắn tin.
