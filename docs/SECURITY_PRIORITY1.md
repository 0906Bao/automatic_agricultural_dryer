# Bảo mật Priority 1

> Cập nhật: MQTT hiện đã chuyển sang TLS cổng 8883 và sequence mới. Xem [hướng dẫn hiện tại](SECURITY_TLS.md); phần Priority 1 mô tả giai đoạn trước chuyển đổi.
Đã triển khai trên hệ thống Windows/Wokwi/HAOS hiện tại: MQTT bắt buộc đăng nhập và kiểm tra ACL; Node-RED có tài khoản quản trị và HTTP riêng; cổng quản trị chỉ bind localhost; MQTT chỉ bind localhost và host VMnet8 `192.168.137.1`.

## Truy cập và credentials

- Node-RED: `http://127.0.0.1:1880`, user `dryer-admin`.
- HTTP dashboard (nếu flow dashboard được bật): user `dryer-operator`, mật khẩu riêng. Runtime hiện được giữ nguyên 16 node, không tự import lại dashboard.
- Home Assistant vẫn truy cập qua cổng 8123 và dùng tài khoản HA hiện có.
- Mật khẩu được sinh ngẫu nhiên trong `.local/security/credentials.json`; thư mục được tắt kế thừa ACL NTFS và chỉ cấp toàn quyền cho người dùng Windows đang triển khai. Không đưa tệp này, firmware đã build hoặc backup ra Git/chia sẻ công khai.
- Mosquitto chỉ được mount tệp hash `.local/security/passwords`; Node-RED chỉ được mount `.local/security/node-red-auth.json` chứa bcrypt hash, không mount toàn bộ kho credentials.
- MQTT: `dryer-esp` chỉ xuất dữ liệu/trạng thái và nhận lệnh; `dryer-nodered` chạy bridge; `dryer-homeassistant` chỉ gửi yêu cầu qua `dryer/ha/command`, không có quyền publish telemetry hoặc lệnh ESP trực tiếp. Xem `mosquitto/acl.example`.

## Triển khai lại trên máy hiện tại

Giữ nguyên các tệp riêng tư và volume đã provision; không chạy lại bước `prepare` để xoay mật khẩu ngoài ý muốn:

```powershell
docker compose config --quiet
docker compose up -d mosquitto node-red
python tools/harden-priority1.py verify
```

`verify` cần Docker Desktop, credentials cục bộ, Wokwi/ESP đang gửi telemetry và Node-RED bridge đang chạy. Nó kiểm tra đăng nhập, từ chối anonymous/mật khẩu sai, ACL đọc/ghi, telemetry và giữ nguyên flow so với bản backup. Nó chỉ xuất gói trạng thái kiểm tra, không phát lệnh motor hợp lệ.

Máy mới cần provision trước khi `compose up`: tạo ba tài khoản Mosquitto bằng `mosquitto_passwd` tương tác, lưu hash vào `.local/security/passwords`; tạo bcrypt hash và tệp `.local/security/node-red-auth.json` gồm `adminUser`, `adminHash`, `httpUser`, `httpHash`. Không dùng mật khẩu trên command line. Cập nhật mọi broker node Node-RED và MQTT integration HA bằng đúng tài khoản; điền `MQTT_USER/PASSWORD` ESP32 trong `include/secrets.local.h`, rồi build/nạp lại firmware. Thiếu tệp xác thực sẽ khiến dịch vụ không khởi động; không có fallback anonymous.

## Firewall và mạng

Chạy từ PowerShell Administrator:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/secure-dryer-firewall.ps1
```

Bốn rule `Dryer-*` chặn nguồn IPv4 ngoài localhost/mạng VMnet8 đối với MQTT, chặn IPv6 unicast từ mạng, cho VMnet8 truy cập MQTT và chặn quản trị Node-RED từ xa. Explicit block ưu tiên hơn rule allow Docker rộng có sẵn. Không thay đổi rule Home Assistant cổng 8123 hoặc tắt firewall. Kết quả lưu trong `.local/security/firewall-result.json`.

Nếu đổi mạng VM: sửa `MQTT_VM_BIND_ADDRESS` trong `.env` và chạy script với `-VmSubnet` đúng subnet private, tối đa /24. ESP32 thật trên Wi-Fi chưa nằm trong danh sách nguồn cho phép; bổ sung đúng IP thiết bị vào bind/allowlist và ngoại lệ của rule block trước khi chuyển sang phần cứng. Không mở `0.0.0.0:1883` đại trà để xử lý lỗi kết nối.

## Backup và phục hồi

Vị trí backup được ghi trong `credentials.json` ở khóa `backup`; có export flow, toàn bộ `/data` Node-RED và cấu hình cũ. Backup volume được đọc khi Node-RED đang chạy: phù hợp cho đối chiếu flow/credentials trong lần chuyển đổi này, không thay thế snapshot nhất quán của toàn bộ dữ liệu động. Backup có bí mật và được hạn chế quyền như credentials.

Khôi phục `/data` phải dừng Node-RED, giữ cả `.config.runtime.json` và `flows_cred.json` để không mất khóa giải mã. Không chỉ import flow rồi xóa volume. Bản cấu hình cũ có anonymous MQTT; không chép đè rồi mở lại mạng ngoài. Nếu cần phục hồi kết nối, giữ firewall/bind hạn chế và đồng bộ tài khoản của cả ba thành phần.

Giai đoạn tiếp theo đã bổ sung TLS, sửa sequence và ghim phụ thuộc; xem [hướng dẫn hiện tại](SECURITY_TLS.md). Khi cần bảo trì tự động, dùng token quản trị Node-RED được cấp hợp lệ; API `/flows` hiện trả 401 nếu không có token.
