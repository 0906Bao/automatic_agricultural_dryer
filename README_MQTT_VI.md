# Hướng dẫn MQTT + Node-RED cho Automatic Agricultural Dryer

## 1. Chạy Mosquitto và Node-RED trên Windows Docker Desktop

Mở PowerShell tại thư mục chứa `docker-compose.yml`:

Cấu hình hiện yêu cầu tài khoản MQTT và Node-RED. Trước khi chạy trên máy mới, provision các tệp xác thực theo [hướng dẫn bảo mật](docs/SECURITY_PRIORITY1.md).

```powershell
docker compose up -d
docker compose ps
docker compose logs -f mosquitto
```

Mở Node-RED: http://localhost:1880

Flow/dashboard đã có sẵn trong `node-red/flows.json`. Compose tự nạp vào volume mới; nếu đã có flow cũ, Import file này rồi Deploy. Mở dashboard tại http://localhost:1880/dryer. Hướng dẫn dưới đây về `mqtt in` chỉ cần nếu tự tạo flow riêng.

Cấu hình `mqtt in` trong Node-RED:
- Server: `mosquitto`
- Port: `8883`
- Topic: `dryer/telemetry`
- TLS: bật kiểm tra chứng thư, CA riêng của deployment.
- Security: tài khoản `dryer-nodered` và mật khẩu đã cấp.
- Nối `mqtt in` -> `json` -> `debug`, sau đó Deploy.

> Mosquitto từ chối anonymous và áp dụng ACL riêng cho từng thành phần. Node-RED chỉ truy cập từ localhost và cần đăng nhập. Không port-forward cổng điều khiển ra Internet.

## 2. Kết nối Wokwi đến MQTT broker chạy cục bộ

Wokwi Public Gateway có Internet đi ra nhưng không truy cập được dịch vụ trên máy Windows. Để mô phỏng ESP32 truy cập Mosquitto cục bộ, cần Wokwi Private IoT Gateway (Wokwi trả phí) hoặc Wokwi for VS Code có gateway phù hợp.

Với Private Gateway:
1. Cài/chạy Wokwi Private IoT Gateway theo tài liệu Wokwi.
2. Trong Wokwi for VS Code, bật `Enable Private Wokwi IoT Gateway` qua Command Palette (F1).
3. Giữ `MQTT_HOST "host.wokwi.internal"` trong `include/secrets.local.h`.
4. Docker publish `127.0.0.1:8883:8883`; gateway chạy trên máy này. Điền tài khoản `dryer-esp`, build và khởi động lại mô phỏng sau khi đổi credentials.

Nếu bạn không có Private Gateway, MQTT tới broker Docker cục bộ sẽ không hoạt động qua Public Gateway. Khi đó cần dùng broker MQTT có thể truy cập qua Internet hoặc chuyển sang ESP32 thật trong cùng LAN.

## 3. Cấu hình Wi-Fi và MQTT

Sao chép `include/secrets.local.h.example` thành `include/secrets.local.h`, rồi điền Wi-Fi và broker MQTT. File local đã được Git bỏ qua. `include/secrets.h` tự nạp file này khi có và cung cấp mặc định không bí mật để build khi chưa có cấu hình local.

## 4. Biên dịch và chạy Wokwi

Trong VS Code mở thư mục project, dùng PlatformIO:
- `PlatformIO: Build`
- Mở Wokwi simulation theo quy trình hiện tại của project.
- Mở Serial Monitor 115200 baud.

Kiểm tra log Wi-Fi, MQTT. MQTT topic dữ liệu: `dryer/telemetry`; trạng thái: `dryer/status`; online/offline: `dryer/availability`.

Payload telemetry JSON gồm `rain_adc`, `light_adc`, `rain`, `dark`, `temperature_c`, `humidity_pct`, `dht_valid`, `humidity_warning`, `humidity_danger`, `cover_request`, `cover_reason`, `limit_covered`, `limit_open`, `session`, `last_command_seq`, `last_command_result`, `mode`, `motion`, `fault`, `estop`, `driver_fault`, `motor_output_enabled`, `motor_active`, `command_result`. Khi DHT lỗi, `temperature_c` và `humidity_pct` là -999; dùng `dht_valid` để xác định tính hợp lệ.

## 5. Giới hạn hiện tại

- Firmware có state machine và đầu ra IN1/IN2/EN, mặc định khóa bằng `MOTOR_OUTPUT_ENABLED=0`; cần chọn driver và nghiệm thu phần cứng trước khi bật.
- `cover_request` thể hiện yêu cầu mái che (logic), không xác nhận vị trí vật lý; dùng `limit_covered` và `limit_open` để xác nhận hành trình.
- Node-RED và Home Assistant gửi STOP/AUTO/OPEN/CLOSE/RESET qua MQTT, dùng chung interlock và chốt lỗi tại ESP32. Không retain lệnh MQTT.
- MQTT dùng TLS với CA riêng, tài khoản và ACL. Kết nối ESP32 thật qua LAN cần bổ sung bind/firewall theo đúng IP thiết bị.

Xem `docs/CONTROL_VI.md` để cấu hình Wi-Fi thật, driver, dừng khẩn, lệnh MQTT và chạy kiểm thử.
