# Hướng dẫn MQTT + Node-RED + Blynk cho Automatic Agricultural Dryer

## 1. Chạy Mosquitto và Node-RED trên Windows Docker Desktop

Mở PowerShell tại thư mục chứa `docker-compose.yml`:

```powershell
docker compose up -d
docker compose ps
docker compose logs -f mosquitto
```

Mở Node-RED: http://localhost:1880

Cấu hình `mqtt in` trong Node-RED:
- Server: `mosquitto`
- Port: `1883`
- Topic: `dryer/telemetry`
- Nối `mqtt in` -> `json` -> `debug`, sau đó Deploy.

> Cấu hình Mosquitto hiện cho phép anonymous, chỉ dành cho lab cục bộ. Không port-forward cổng 1883 ra Internet.

## 2. Kết nối Wokwi đến MQTT broker chạy cục bộ

Wokwi Public Gateway có Internet đi ra nhưng không truy cập được dịch vụ trên máy Windows. Để mô phỏng ESP32 truy cập Mosquitto cục bộ, cần Wokwi Private IoT Gateway (Wokwi trả phí) hoặc Wokwi for VS Code có gateway phù hợp.

Với Private Gateway:
1. Cài/chạy Wokwi Private IoT Gateway theo tài liệu Wokwi.
2. Trong Wokwi for VS Code, bật `Enable Private Wokwi IoT Gateway` qua Command Palette (F1).
3. Giữ `MQTT_HOST "host.wokwi.internal"` trong `include/secrets.h`.
4. Đảm bảo Docker publish cổng `1883:1883` và Windows Firewall không chặn kết nối từ gateway.

Nếu bạn không có Private Gateway, firmware vẫn có thể kết nối Blynk Cloud qua Public Gateway, nhưng MQTT tới broker Docker cục bộ sẽ không hoạt động. Khi đó cần dùng broker MQTT có thể truy cập qua Internet hoặc chuyển sang ESP32 thật trong cùng LAN.

## 3. Thiết lập Blynk IoT Cloud

1. Vào https://blynk.cloud/ và đăng nhập.
2. Developer Zone -> My Templates -> Create New Template.
3. Hardware: ESP32; Connection Type: WiFi.
4. Trong Datastreams, tạo Virtual Pin datastreams:
   - V0: Temperature, Double, °C, khoảng -20..100
   - V1: Humidity, Double, %, khoảng 0..100
   - V2: Rain ADC, Integer, 0..4095
   - V3: Light ADC, Integer, 0..4095
   - V4: Is raining, Integer, 0..1
   - V5: Is dark, Integer, 0..1
   - V6: Cover request close, Integer, 0..1
5. Tạo Device từ Template, mở Device Info và lấy Template ID cùng Device Auth Token.
6. Điền chúng vào `include/secrets.h`:
   - `BLYNK_TEMPLATE_ID`
   - `BLYNK_TEMPLATE_NAME`
   - `BLYNK_AUTH_TOKEN`
7. Trong Web Dashboard/Mobile Dashboard, thêm Value Display/Gauge/LED phù hợp và gán từng widget vào datastream tương ứng.

Không chia sẻ Device Auth Token công khai. Nếu lộ token, hãy tạo lại token trong Blynk.

## 4. Biên dịch và chạy Wokwi

Trong VS Code mở thư mục project, dùng PlatformIO:
- `PlatformIO: Build`
- Mở Wokwi simulation theo quy trình hiện tại của project.
- Mở Serial Monitor 115200 baud.

Kiểm tra log Wi-Fi, MQTT, Blynk. MQTT topic dữ liệu: `dryer/telemetry`; trạng thái: `dryer/status`; online/offline: `dryer/availability`.

Payload telemetry JSON gồm `rain_adc`, `light_adc`, `rain`, `dark`, `temperature_c`, `humidity_pct`, `cover_request`, `limit_covered`, `limit_open`.

## 5. Giới hạn hiện tại

- Firmware giữ nguyên logic cảm biến/ra quyết định hiện có; chưa điều khiển động cơ thật.
- V6 thể hiện yêu cầu đóng mái che (logic), không xác nhận mái che đã đóng vật lý.
- Chưa triển khai lệnh điều khiển từ Node-RED/Blynk để tránh tạo cảm giác có thể điều khiển động cơ khi project chưa có phần chấp hành.
- Mosquitto config là cấu hình thử nghiệm không xác thực. Chỉ sử dụng trong mạng tin cậy.
