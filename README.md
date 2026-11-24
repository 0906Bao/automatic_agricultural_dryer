# Automatic Agricultural Dryer — Hệ thống phơi nông sản tự động

## 1. Mô tả project

Project xây dựng hệ thống IoT dùng ESP32 để giám sát điều kiện phơi nông sản và điều khiển mái che. Hệ thống đọc cảm biến mưa, ánh sáng và DHT22 (nhiệt độ, độ ẩm), từ đó quyết định đóng hoặc mở mái che để bảo vệ nông sản.

Các chức năng chính:

- Giám sát môi trường và gửi dữ liệu, trạng thái thiết bị qua MQTT.
- Tự động yêu cầu đóng mái khi có mưa, trời tối, độ ẩm trên 80% hoặc DHT lỗi, sau khi xác nhận điều kiện nguy hiểm trong 500 ms.
- Chỉ cho phép mở sau 10 giây liên tục không mưa, đủ sáng, DHT hợp lệ và độ ẩm dưới 70%. Quy tắc này áp dụng cả cho lệnh mở thủ công.
- Điều khiển bằng các lệnh `AUTO`, `OPEN`, `CLOSE`, `STOP`, `RESET` trên dashboard.
- Giám sát hành trình đóng/mở, dừng khẩn, lỗi driver và thời gian chạy motor (mặc định tối đa 20 giây).
- Theo dõi bằng Node-RED, tích hợp Home Assistant OS trên VMware và mô phỏng bằng Wokwi.

Luồng hoạt động: **ESP32 / Wokwi ↔ MQTT Mosquitto ↔ Node-RED / Home Assistant**. Logic điều khiển mái che chạy trên ESP32; Docker cung cấp broker và giao diện giám sát.

| Thành phần | Vai trò |
| --- | --- |
| `src/main.cpp` | Đọc cảm biến, kết nối Wi-Fi/MQTT, điều khiển ESP32 |
| `include/` | Logic điều khiển, quy tắc thời tiết, cấu hình phần cứng |
| `diagram.json`, `wokwi.toml` | Sơ đồ và cấu hình mô phỏng Wokwi |
| `docker-compose.yml`, `mosquitto/` | Dịch vụ Docker và broker MQTT |
| `node-red/flows.json` | Dashboard và luồng xử lý MQTT |
| `home-assistant/` | Cấu hình tích hợp Home Assistant |

## 2. Hướng dẫn chạy chương trình

Thực hiện các lệnh tại thư mục gốc của project, nơi chứa `platformio.ini` và `docker-compose.yml`.

### 2.1. Chuẩn bị

- Cài Visual Studio Code và extension **PlatformIO IDE**. Chạy các lệnh `pio` trong terminal PlatformIO.
- Cài và khởi động **Docker Desktop** có hỗ trợ Docker Compose.
- Nếu mô phỏng: cài **Wokwi for VS Code** và cấu hình quyền sử dụng Wokwi tương ứng. Kết nối từ Wokwi tới broker trên máy tính cần **Private IoT Gateway**.
- Nếu chạy thực tế: chuẩn bị ESP32, cáp USB, cảm biến, driver motor và các công tắc theo bảng chân kết nối ở mục 2.5.

### 2.2. Cấu hình Wi-Fi và MQTT

Nếu chưa có `include/secrets.local.h`, sao chép file mẫu bằng PowerShell:

```powershell
Copy-Item include/secrets.local.h.example include/secrets.local.h
```

Nếu file đã tồn tại, chỉnh sửa trực tiếp và giữ lại cấu hình của máy. Điền các giá trị:

| Cấu hình | Wokwi | ESP32 thật |
| --- | --- | --- |
| `WIFI_SSID` | `"Wokwi-GUEST"` | Tên Wi-Fi 2.4 GHz |
| `WIFI_PASSWORD` | `""` | Mật khẩu Wi-Fi |
| `MQTT_HOST` | `"host.wokwi.internal"` | IP LAN của máy chạy Docker |
| `MQTT_PORT` | `1883` | `1883` |
| `MQTT_USER`, `MQTT_PASSWORD` | Để trống với broker lab mặc định | Điền nếu broker yêu cầu xác thực |

`include/secrets.h` tự nạp cấu hình local. File `secrets.local.h` đã được Git bỏ qua; không đưa thông tin đăng nhập thật vào repository.

### 2.3. Khởi động MQTT và Node-RED

```powershell
docker compose up -d mosquitto node-red
docker compose ps
```

Compose tự chạy dịch vụ khởi tạo flow mà Node-RED phụ thuộc. Với volume mới, flow mẫu được nạp tự động. Nếu volume đã có flow cũ, mở trình chỉnh sửa Node-RED, chọn **Import**, nhập `node-red/flows.json` rồi **Deploy**.

- Trình chỉnh sửa: [http://localhost:1880](http://localhost:1880).
- Dashboard điều khiển: [http://localhost:1880/dryer](http://localhost:1880/dryer).
- Broker MQTT: cổng `1883` trên máy chạy Docker.

Broker mặc định cho phép kết nối không xác thực, dành cho thử nghiệm trong mạng tin cậy. Không công khai cổng `1883` ra Internet.

### 2.4. Chạy mô phỏng Wokwi

1. Cấu hình Wi-Fi và MQTT dành cho Wokwi như mục 2.2.
2. Khởi động Private IoT Gateway, sau đó bật **Enable Private Wokwi IoT Gateway** trong Command Palette của VS Code.
3. Biên dịch firmware mô phỏng:

   ```powershell
   pio run -e wokwi
   ```

4. Mở Command Palette (`F1`), chọn **Wokwi: Start Simulator**. `wokwi.toml` đã trỏ đến firmware trong `.pio/build/wokwi/`.
5. Mở dashboard Node-RED để xem dữ liệu và điều khiển. Sau mỗi lần build lại, dừng rồi khởi động lại mô phỏng để dùng firmware mới.

Trong mô phỏng, công tắc **LIMIT CLOSE / LIMIT OPEN** ở bên trái là chưa chạm, bên phải là đã chạm; công tắc dừng khẩn ở bên trái là bình thường. Môi trường `wokwi` bật GPIO motor để thử bằng LED và tự mô phỏng hành trình (5 giây cho toàn hành trình). Để cả LIMIT CLOSE / LIMIT OPEN bên trái khi chạy tự động; không cần gạt công tắc mỗi lần mở/đóng. AUTO giữ bật khi tới đích và tự đóng khi mưa; công tắc vẫn dùng để ép vị trí khi thử thủ công. Bản `esp32dev` chỉ dùng hành trình vật lý.

### 2.5. Chạy trên ESP32 thật

Kết nối phần cứng theo bảng:

| Thiết bị / tín hiệu | GPIO ESP32 |
| --- | --- |
| Cảm biến mưa (analog) | 34 |
| Cảm biến ánh sáng (analog) | 35 |
| DHT22 | 15 |
| Hành trình đóng / mở (NO xuống GND) | 18 / 19 |
| LED yêu cầu che | 23 |
| Driver motor IN1 / IN2 / EN | 25 / 26 / 27 |
| Dừng khẩn (NC xuống GND) | 21 |
| Lỗi driver tùy chọn (active LOW) | 22 |

Điền Wi-Fi thật và IP LAN của máy Docker trong `include/secrets.local.h`, kết nối ESP32 qua USB, rồi chạy:

```powershell
pio run -e esp32dev
pio run -e esp32dev -t upload
pio device monitor -b 115200
```

Nếu PlatformIO không tự chọn đúng cổng, thêm `--upload-port COMx` vào lệnh upload và `-p COMx` vào lệnh monitor; thay `COMx` bằng cổng thực tế.

**Bản `esp32dev` mặc định khóa đầu ra motor (`MOTOR_OUTPUT_ENABLED=0`).** Chỉ đổi thành `1` trong `include/secrets.local.h` rồi build/nạp lại sau khi kiểm tra driver, nguồn, chiều quay, hành trình và dừng khẩn. Không nạp bản `wokwi` lên motor thật chưa kiểm tra.

### 2.6. Theo dõi và điều khiển

Hệ thống khởi động ở trạng thái `STOPPED`. Sau khi dashboard nhận dữ liệu:

1. Kiểm tra cảm biến, hành trình và dừng khẩn.
2. Chọn **Tự động** (`AUTO`) để chạy theo môi trường, hoặc **Mở bạt / Đóng bạt** (`OPEN` / `CLOSE`) để điều khiển thủ công.
3. Chọn **Dừng** (`STOP`) để giữ hệ thống dừng cho tới lệnh tiếp theo.
4. Khi có lỗi, xử lý nguyên nhân rồi chọn **Xóa lỗi** (`RESET`). Hệ thống trở về `STOPPED`; cần chọn lệnh để chạy tiếp.

MQTT dùng các topic `dryer/telemetry` (dữ liệu), `dryer/status` (phản hồi), `dryer/availability` (online/offline) và `dryer/command` (lệnh). Dashboard tự tạo lệnh theo phiên và số thứ tự mà firmware yêu cầu.

Nếu dashboard không có dữ liệu, kiểm tra Wi-Fi, `MQTT_HOST`, gateway Wokwi và firewall cổng `1883`. Xem log bằng:

```powershell
docker compose logs --tail 100 mosquitto node-red
```

Dừng các dịch vụ và giữ lại dữ liệu:

```powershell
docker compose stop node-red mosquitto
```

### 2.7. Home Assistant (tùy chọn)

Project hỗ trợ Home Assistant OS trên VMware. Service Docker `ha-access` chỉ chuyển tiếp kết nối đến máy ảo; cần cài và khởi động HAOS riêng theo [hướng dẫn Home Assistant](docs/HOME_ASSISTANT_SETUP.md).

Sau khi thiết lập HAOS, cấu hình `HA_VM_ADDRESS` và `HA_VM_PORT` trong `.env` theo `.env.example`, rồi bật gateway:

```powershell
docker compose up -d ha-access
```

Truy cập [http://localhost:8123](http://localhost:8123), mở dashboard `/dryer-dashboard/overview` sau khi hoàn tất tích hợp.

Chi tiết bổ sung: [MQTT và Node-RED](README_MQTT_VI.md), [điều khiển và kiểm tra phần cứng](docs/CONTROL_VI.md).
