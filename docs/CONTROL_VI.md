# Điều khiển mái che và đưa lên phần cứng

## 1. Cấu hình theo máy

Sao chép `include/secrets.local.h.example` thành `include/secrets.local.h` nếu chưa có. Nếu đã có, bổ sung các macro còn thiếu:

```cpp
#define WIFI_SSID "TEN_WIFI_CUA_BAN"
#define WIFI_PASSWORD "MAT_KHAU_WIFI"
#define WIFI_CHANNEL 0
#define MQTT_HOST "192.168.1.10" // IP máy chạy Docker trong LAN
#define MOTOR_OUTPUT_ENABLED 0
#define MOTOR_TRAVEL_TIMEOUT_MS 20000UL
```

Wokwi dùng `Wokwi-GUEST`, mật khẩu rỗng. `WIFI_CHANNEL = 0` tự tìm kênh. ESP32 thật cần Wi-Fi 2.4 GHz. Không commit file local. Cấu hình mặc định khi không có file local vẫn build được.

## 2. Giao diện driver

| Tín hiệu | GPIO | Quy ước |
| --- | ---: | --- |
| IN1 | 25 | HIGH khi mở |
| IN2 | 26 | HIGH khi đóng |
| EN | 27 | HIGH cho phép chạy; LOW tắt driver |
| Limit đóng | 18 | NO xuống GND, LOW = chạm hành trình |
| Limit mở | 19 | NO xuống GND, LOW = chạm hành trình |
| Dừng khẩn | 21 | Tiếp điểm NC xuống GND: LOW bình thường, HIGH khi nhấn/đứt dây |
| Driver fault | 22 | LOW = driver báo lỗi; để hở khi không sử dụng |
| LED yêu cầu tự động | 23 | HIGH = yêu cầu che; không xác nhận vị trí |
| Mưa / ánh sáng / DHT22 | 34 / 35 / 15 | Giữ nguyên cảm biến hiện tại |

Đây là driver trừu tượng IN1/IN2/EN active-high, không mặc định tương thích mọi module. Driver phải có mức logic 3.3 V phù hợp và chịu được điện áp, dòng khởi động/kẹt của motor. Không nối motor vào ESP32. Dùng nguồn motor riêng, chung GND và điện trở kéo xuống EN để driver tắt trong lúc reset/boot.

Riêng mô phỏng: `pio run -e wokwi` định nghĩa `DRYER_WOKWI_SIMULATION=1`, bật đầu ra motor kể cả khi file local đang đặt MOTOR_OUTPUT_ENABLED=0. `wokwi.toml` dùng `.pio/build/wokwi/firmware.bin`. Bản `esp32dev` và lệnh `pio run` mặc định vẫn khóa motor nếu chưa mở khóa phần cứng trong local config. Sau build, dừng/chạy lại mô phỏng; chọn AUTO/CLOSE/OPEN theo điều kiện cho phép, gạt hành trình đích sang phải trước timeout để mô phỏng dừng. Không có motor vật lý tự kéo hay tự nhấn hành trình trong sơ đồ.

Chỉ đặt `MOTOR_OUTPUT_ENABLED 1` sau khi xác minh cực tính, chiều quay, driver và nguồn. Với giá trị 0, state machine vẫn hoạt động để mô phỏng nhưng GPIO motor luôn LOW; `motor_active` luôn false. Thời gian 20 giây chỉ là mặc định để thử, cần đo hành trình thực và chọn giới hạn phù hợp.

Dừng khẩn phải có đường cắt nguồn/enable driver bằng phần cứng độc lập; GPIO21 chỉ giám sát thêm. Công tắc hành trình phần mềm hiện dùng NO nên không phát hiện được đứt dây; cần bảo vệ giới hạn cơ/điện độc lập. GPIO22 cần ngõ ra open-drain hoặc logic 3.3 V; không đưa tín hiệu 5 V vào ESP32.

## 3. Trạng thái và quy tắc

- Khởi động ở `STOPPED`, không tự chạy sau mất điện. Chọn `AUTO`, `OPEN` hoặc `CLOSE` để bắt đầu.
- `AUTO`: mưa, tối, độ ẩm >80% hoặc DHT lỗi liên tục 500 ms yêu cầu đóng. Mở sau 30 giây khô, sáng, DHT hợp lệ và độ ẩm <70%. Khởi động mặc định yêu cầu che, nên phải có đủ 30 giây an toàn trước yêu cầu mở.
- `OPEN`: lệnh thủ công chỉ được nhận sau 30 giây liên tục khô, sáng, DHT hợp lệ, độ ẩm <70%. Nếu sau đó xuất hiện nguy hiểm, tự chuyển sang `MANUAL_CLOSE`. Vùng 70–80% chỉ cảnh báo, không ép đóng.
- `CLOSE`: đóng tới công tắc hành trình đóng.
- `STOP`: dừng và giữ `STOPPED`, không tự chạy lại do cảm biến đổi.
- Đảo chiều: tắt EN và cả IN1/IN2, đợi ít nhất 300 ms trước hướng ngược lại. Khởi động chuyển động cũng có thời gian nghỉ 300 ms.
- Chạm công tắc đích: dừng ngay trong chu kỳ tác vụ; không tự chạy lại khi tiếp điểm nhả do rung. Đổi mục tiêu/chế độ mới cho phép hành trình khác.
- Hai hành trình cùng kích hoạt, dừng khẩn, driver fault hoặc quá thời gian chạy: tắt đầu ra và chốt lỗi. `RESET` chỉ được nhận khi đầu vào lỗi đã hết; sau reset vẫn `STOPPED`.
- Timeout phát hiện **không tới hành trình đúng hạn**, không đo trực tiếp dòng kẹt. Nếu driver có bảo vệ dòng/overload, nối ngõ fault vào GPIO22. Không tự thử chạy lại sau lỗi.
- Tác vụ motor ưu tiên cao kiểm tra đầu vào mỗi khoảng 5 ms, độc lập với vòng lặp mạng. Đây không phải cam kết thời gian dừng chứng nhận; phần cứng phải cắt motor độc lập. Nếu quyết định cảm biến không cập nhật quá 10 giây, tác vụ dùng yêu cầu đóng và cấm mở. Trong `STOPPED` hoặc trạng thái lỗi, quy tắc này không tự kích hoạt motor.
- Mất MQTT không hủy một chuyển động đang được giám sát bằng hành trình/timeout. Lệnh STOP trên mạng không thay thế dừng khẩn vật lý. Khi đầu ra motor đã bật và đang chuyển động, firmware trì hoãn thử kết nối lại MQTT. Khi đầu ra bị khóa để mô phỏng, vẫn thử kết nối lại bình thường.

`cover_request` là ý định tự động từ thời tiết; `mode`, `motion`, `fault`, `limit_*` và `motor_active` mô tả phần điều khiển. Không suy ra vị trí từ LED hay `cover_request`. Khi không công tắc nào active, vị trí chưa xác định/ở giữa hành trình.

## 4. MQTT và dashboard Node-RED

Chạy tại thư mục gốc:

```powershell
docker compose up -d
docker compose ps -a
```

Lần đầu với volume mới, `node-red-init` chép flow mẫu vào `/data/flows.json` và thoát thành công. Đây là service một lần, trạng thái Exited (0) là bình thường. **Volume có flow sẵn được giữ nguyên.** Khi đó mở editor [Node-RED](http://localhost:1880), Menu → Import → chọn `node-red/flows.json`, bỏ flow cũ có route `/dryer` nếu trùng, Deploy. Không chạy cả hai compose root và `iot-platform` cùng lúc vì dùng chung tên container/cổng.

Mở [dashboard](http://localhost:1880/dryer). Dashboard dùng HTTP/Template/Function/MQTT có sẵn, không cần cài dashboard palette. Có hiển thị số đo, trạng thái, hành trình, lỗi và 5 nút lệnh. Dữ liệu quá 10 giây bị đánh dấu offline và khóa nút. DHT lỗi/offline hiển thị nhiệt độ/độ ẩm không hợp lệ. Phản hồi HTTP 202 chỉ là đã xếp lệnh; dashboard đợi `last_command_seq` từ thiết bị để xác nhận nhận/xử lý.

| Topic | Chức năng |
| --- | --- |
| `dryer/telemetry` | JSON mỗi 1 giây theo đồng hồ ESP32; không retain. Wokwi chạy chậm có thể làm khoảng cách thực tế dài hơn |
| `dryer/availability` | online/offline có retain và LWT |
| `dryer/status` | Trạng thái kết nối hoặc kết quả lệnh, không retain |
| `dryer/command` | Lệnh QoS1, **không retain** |

Payload lệnh: `<session> <sequence> <COMMAND>`. Ví dụ `deadbeef 123 AUTO`, trong đó session phải lấy từ telemetry của lần boot hiện tại; sequence là số nguyên dương tăng dần, tối đa 9007199254740991. Lệnh hợp lệ: `STOP AUTO OPEN CLOSE RESET`. Dashboard tự tạo envelope. Thiết bị từ chối session cũ, sequence trùng/thấp hơn và lệnh không hợp lệ. `last_command_result` đi cùng `last_command_seq` báo kết quả lệnh MQTT cuối; `command_result` là kết quả gần nhất từ bất kỳ nguồn điều khiển nào. Cơ chế sequence chống phát lại qua reconnect/boot, **không xác thực người gửi**; tuyệt đối không retain lệnh. Lệnh retain chưa từng được xử lý trong cùng session vẫn có thể chạy khi subscribe lại, nên xóa retained command nếu broker từng có.

API dashboard: GET `/dryer/state`, POST `/dryer/command` với JSON `{"command":"AUTO"}`. MQTT và HTTP hiện dành cho lab trong mạng tin cậy, chưa có authentication/TLS. Không mở port điều khiển ra Internet. Khi triển khai thật, cấu hình xác thực Mosquitto và Node-RED, đồng thời cập nhật MQTT_USER/PASSWORD.

Mã giao diện: `node-red/dashboard.html`; Function nodes: `node-red/functions/`. Sau khi sửa, chạy `node tools/build-flow.cjs` rồi import lại flow. File `flows.json` là bản export được sinh từ các nguồn này.

## 5. Kiểm thử

Windows có Visual Studio C++ tools và Node.js:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File test/run-host.ps1
```

Linux/macOS có C++ compiler và Node.js: `sh test/run-host.sh`.

Kiểm thử chạy trực tiếp các lớp C++ firmware, không dùng bản mô phỏng lại bằng ngôn ngữ khác: boot dừng, hai hướng và hành trình, rung công tắc, đảo chiều, STOP giữ dừng, timeout không bị reset bởi lệnh trùng, chốt/reset lỗi, dừng khẩn, driver fault, cấm mở nguy hiểm, timer tràn và chuỗi đầu vào trộn. Kiểm thử Node.js kiểm tra cache/freshness, lệnh, sequence, HTTP và tính đồng bộ của flow export. GitHub Actions còn build firmware với cấu hình mặc định không có secrets.

Build phần cứng: `pio run -e esp32dev`. Build Wokwi bật GPIO motor: `pio run -e wokwi`, rồi dừng/chạy lại mô phỏng. Nếu đã đổi đường dẫn firmware trong `wokwi.toml` nhưng vẫn thấy `outputs=LOCKED`, chạy **Developer: Reload Window**, rồi **Wokwi: Start Simulator** để bỏ cấu hình cũ của phiên Wokwi. Kiểm tra Serial `outputs=ENABLED` và HA “Đầu ra motor: Đã bật đầu ra”. Sơ đồ Wokwi có công tắc trượt dừng khẩn (trái = bình thường, phải = lỗi), nút driver fault, hai công tắc trượt hành trình (trái = chưa chạm, phải = đã chạm) và ba LED IN1/IN2/EN. Không nạp bản Wokwi lên motor thật chưa nghiệm thu.

Wokwi chưa có mô hình motor vật lý tự nhấn hành trình. Khi chạy mở/đóng, trước 20 giây của ESP32, gạt **LIMIT OPEN hoặc LIMIT CLOSE sang phải** để xác nhận hành trình đích; gạt lại về trái để nhả trước khi chạy ngược chiều. Không kích hoạt hai hành trình cùng lúc. Khi chạm hành trình, motor dừng nhưng AUTO vẫn bật. Nếu không chạm, `MOTION_TIMEOUT` chốt lỗi, AUTO tắt; kiểm tra rồi nhấn **Xóa lỗi**, sau đó chọn lại chế độ. Mở thủ công vẫn cần khô, sáng, DHT hợp lệ và độ ẩm dưới 70% liên tục 30 giây. Firmware và dashboard hiển thị riêng lỗi quá thời gian, dừng khẩn, hai hành trình, driver và điều kiện mở.

Host tests không kiểm chứng GPIO, độ trễ scheduler, dòng motor hoặc dịch vụ cloud. Cần nghiệm thu thực tế: chiều quay, công tắc đúng đầu, hai công tắc cùng active, dừng khẩn và đứt dây NC, driver fault, kẹt/quá thời gian, mất Wi-Fi, mất nguồn rồi khởi động lại. Từ khóa lỗi: `ESTOP`, `BOTH_LIMITS`, `DRIVER_FAULT`, `MOTION_TIMEOUT`.

## Tài liệu tham khảo

- [Node-RED HTTP endpoint](https://cookbook.nodered.org/http/create-an-http-endpoint)
- [Node-RED Function nodes](https://nodered.org/docs/user-guide/writing-functions)
- [Wokwi slide switch](https://docs.wokwi.com/parts/wokwi-slide-switch)
