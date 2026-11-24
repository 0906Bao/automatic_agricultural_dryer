# Điều khiển mái che và đưa lên phần cứng

> Cập nhật: MQTT hiện đã chuyển sang TLS cổng 8883 và sequence mới. Xem [hướng dẫn hiện tại](SECURITY_TLS.md); phần Priority 1 mô tả giai đoạn trước chuyển đổi.
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

Riêng mô phỏng: `pio run -e wokwi` định nghĩa `DRYER_WOKWI_SIMULATION=1`, bật đầu ra motor kể cả khi file local đang đặt MOTOR_OUTPUT_ENABLED=0. `wokwi.toml` dùng `.pio/build/wokwi/firmware.bin`. Bản `esp32dev` và lệnh `pio run` mặc định vẫn khóa motor nếu chưa mở khóa phần cứng trong local config. Sau build, dừng/chạy lại mô phỏng; chọn AUTO/CLOSE/OPEN theo điều kiện cho phép. Bản Wokwi mô phỏng vị trí và tự kích hoạt hành trình khi chạy tới đích (5 giây cho toàn hành trình), nên không cần gạt công tắc sau mỗi lệnh. Vị trí ban đầu ở giữa hành trình; STOP và thời gian nghỉ đảo chiều giữ nguyên vị trí. Bản esp32dev vẫn chỉ dùng công tắc vật lý.

Chỉ đặt `MOTOR_OUTPUT_ENABLED 1` sau khi xác minh cực tính, chiều quay, driver và nguồn. Với giá trị 0, state machine vẫn hoạt động nhưng GPIO motor luôn LOW; `motor_active` luôn false. Thời gian 20 giây chỉ là mặc định để thử, cần đo hành trình thực và chọn giới hạn phù hợp.

Dừng khẩn phải có đường cắt nguồn/enable driver bằng phần cứng độc lập; GPIO21 chỉ giám sát thêm. Công tắc hành trình phần mềm hiện dùng NO nên không phát hiện được đứt dây; cần bảo vệ giới hạn cơ/điện độc lập. GPIO22 cần ngõ ra open-drain hoặc logic 3.3 V; không đưa tín hiệu 5 V vào ESP32.

## 3. Trạng thái và quy tắc

- Khởi động ở `STOPPED`, không tự chạy sau mất điện. Chọn `AUTO`, `OPEN` hoặc `CLOSE` để bắt đầu.
- `AUTO`: mưa, tối, độ ẩm >80% hoặc DHT lỗi liên tục 500 ms yêu cầu đóng. Mở sau 10 giây khô, sáng, DHT hợp lệ và độ ẩm <70%. Khởi động mặc định yêu cầu che, nên phải có đủ 10 giây an toàn trước yêu cầu mở.
- Độ ẩm **70–80%**: đề xuất **đóng bạt**, chỉ mang tính khuyến nghị; không đổi mục tiêu motor chỉ vì mức ẩm này. `cover_request` là đề xuất cho người dùng, tách khỏi `weather.close` là mục tiêu AUTO. Nếu muốn thực hiện đề xuất, nhấn Đóng bạt. Bảo vệ mưa/tối/DHT lỗi/độ ẩm >80% vẫn áp dụng, kể cả khi đã có đề xuất độ ẩm cao.
- `OPEN`: lệnh thủ công chỉ được nhận sau 10 giây liên tục khô, sáng, DHT hợp lệ, độ ẩm <70%. Nếu sau đó xuất hiện nguy hiểm, tự chuyển sang `MANUAL_CLOSE`. Vùng 70–80% chỉ cảnh báo, không ép đóng.
- `CLOSE`: đóng tới công tắc hành trình đóng.
- `STOP`: dừng và giữ `STOPPED`, không tự chạy lại do cảm biến đổi.
- Đảo chiều: tắt EN và cả IN1/IN2, đợi ít nhất 300 ms trước hướng ngược lại. Khởi động chuyển động cũng có thời gian nghỉ 300 ms.
- Chạm công tắc đích: dừng ngay trong chu kỳ tác vụ; không tự chạy lại khi tiếp điểm nhả do rung. Đổi mục tiêu/chế độ mới cho phép hành trình khác.
- Hai hành trình cùng kích hoạt, dừng khẩn, driver fault hoặc quá thời gian chạy: tắt đầu ra và chốt lỗi. `RESET` chỉ được nhận khi đầu vào lỗi đã hết; sau reset vẫn `STOPPED`.
- Timeout phát hiện **không tới hành trình đúng hạn**, không đo trực tiếp dòng kẹt. Nếu driver có bảo vệ dòng/overload, nối ngõ fault vào GPIO22. Không tự thử chạy lại sau lỗi.
- Tác vụ motor ưu tiên cao kiểm tra đầu vào mỗi khoảng 5 ms, độc lập với vòng lặp mạng. Đây không phải cam kết thời gian dừng chứng nhận; phần cứng phải cắt motor độc lập. Nếu quyết định cảm biến không cập nhật quá 10 giây, tác vụ dùng yêu cầu đóng và cấm mở. Trong `STOPPED` hoặc trạng thái lỗi, quy tắc này không tự kích hoạt motor.
- Mất MQTT không hủy một chuyển động đang được giám sát bằng hành trình/timeout. Lệnh STOP trên mạng không thay thế dừng khẩn vật lý. Khi đầu ra motor đã bật và đang chuyển động, firmware trì hoãn thử kết nối lại MQTT. Khi đầu ra bị khóa để mô phỏng, vẫn thử kết nối lại bình thường.

`cover_request` là đề xuất theo thời tiết cho người dùng, không phải lệnh motor: mức ẩm 70–80% vẫn có thể đề xuất đóng khi mục tiêu AUTO không đổi. `mode`, `motion`, `fault`, `limit_*` và `motor_active` mô tả phần điều khiển. Không suy ra vị trí từ LED hay `cover_request`. Khi không công tắc nào active, vị trí chưa xác định/ở giữa hành trình.

### Theo dõi thời gian chờ mở bạt

Home Assistant tạo thông báo mới trong mục **Thông báo** mỗi khi đề xuất đóng/mở hoặc các điều kiện an toàn thay đổi (mưa, sáng/tối, DHT, mức độ ẩm, đủ điều kiện mở, lỗi, dừng khẩn, hành trình). Thông báo chứa đề xuất, nguyên nhân, mức an toàn và độ ẩm; cảnh báo 70–80% nêu rõ không tự đóng. Trạng thái theo dõi là một snapshot MQTT, nên cập nhật độ ẩm trong cùng mức hoặc đếm ngược từng giây không làm lặp thông báo. Chỉ thông báo khi có dữ liệu hợp lệ; mất kết nối có thông báo riêng. Khi kết nối trở lại, snapshot đầu tiên được thông báo để người dùng biết trạng thái mới nhất.

Dashboard Home Assistant dùng thẻ `dryer-status-card` của dự án để hiển thị biểu tượng và màu theo trạng thái: xanh lá = bình thường/đủ điều kiện, vàng = cảnh báo/đang chờ, đỏ = nguy hiểm/lỗi, xanh dương = hoạt động/thông tin, xám = không kích hoạt hoặc chưa xác nhận. Chữ mô tả vẫn luôn được hiển thị. Khi mất kết nối, thẻ chuyển xám và không giữ màu xanh của dữ liệu cũ. Nhấn vào một dòng để xem lịch sử/thông tin entity.

Tài nguyên frontend: chép `home-assistant/www/dryer-status-card.js` vào `/config/www/dryer-status-card.js`, đăng ký Dashboard resource `/local/dryer-status-card.js` kiểu JavaScript module (không cần HACS). Với HAOS trong dự án, `python tools/deploy-ha-config.py` sao lưu, kiểm tra cấu hình, chép module, reload và tự đăng ký resource; URL chứa phiên bản theo nội dung để tránh dùng cache cũ. Tải lại trang sau khi cập nhật giao diện.

Home Assistant và dashboard Node-RED có mục **Chờ điều kiện mở bạt**, hiển thị số giây còn lại trong khoảng chờ 10 giây. Tiến độ lấy trực tiếp từ ESP32, không tự đếm theo đồng hồ trình duyệt. Ví dụ: **Còn 18 giây · đã ổn định 12/10 giây**. Khi có mưa, trời tối, DHT lỗi hoặc độ ẩm từ 70%, giao diện báo lý do chưa đếm; khi điều kiện an toàn trở lại, tính lại đủ 10 giây. Giao diện cũng phân biệt AUTO tắt, đang có lỗi, mất kết nối và đủ điều kiện mở.

Telemetry `open_wait_remaining_s`: `-1` khi điều kiện chưa an toàn, `1..10` là số giây còn lại (làm tròn lên), `0` khi đủ 10 giây an toàn. Firmware cũ chưa có trường này vẫn được bridge chấp nhận, nhưng giao diện báo chờ dữ liệu thời gian. Sau khi build firmware mới, cần dừng/chạy lại Wokwi hoặc nạp firmware cho ESP32 để có dữ liệu đếm ngược. Trên Home Assistant, hai entity là `sensor.dryer_open_wait_remaining` và `sensor.dryer_open_wait_status`.

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

API dashboard (nếu flow này được bật): GET `/dryer/state`, POST `/dryer/command` với JSON `{"command":"AUTO"}`. MQTT dùng TLS cổng 8883 với tài khoản/ACL; quản trị Node-RED và HTTP dashboard dùng tài khoản riêng. HTTP giao diện chưa có TLS và Node-RED chỉ bind localhost; MQTT chỉ bind localhost và mạng VM. Xem [TLS](SECURITY_TLS.md) trước khi dùng ESP32 thật qua LAN. Không mở port điều khiển ra Internet.

Mã giao diện: `node-red/dashboard.html`; Function nodes: `node-red/functions/`. Sau khi sửa, chạy `node tools/build-flow.cjs` rồi import lại flow. File `flows.json` là bản export được sinh từ các nguồn này.

## 5. Kiểm thử

Windows có Visual Studio C++ tools và Node.js:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File test/run-host.ps1
```

Linux/macOS có C++ compiler và Node.js: `sh test/run-host.sh`.

Kiểm thử chạy trực tiếp các lớp C++ firmware, không dùng bản mô phỏng lại bằng ngôn ngữ khác: boot dừng, hai hướng và hành trình, rung công tắc, đảo chiều, STOP giữ dừng, timeout không bị reset bởi lệnh trùng, chốt/reset lỗi, dừng khẩn, driver fault, cấm mở nguy hiểm, timer tràn và chuỗi đầu vào trộn. Kiểm thử Node.js kiểm tra cache/freshness, lệnh, sequence, HTTP và tính đồng bộ của flow export. GitHub Actions còn build firmware với cấu hình mặc định không có secrets.

Build phần cứng: `pio run -e esp32dev`. Build Wokwi bật GPIO motor: `pio run -e wokwi`, rồi dừng/chạy lại mô phỏng. Nếu đã đổi đường dẫn firmware trong `wokwi.toml` nhưng vẫn thấy `outputs=LOCKED`, chạy **Developer: Reload Window**, rồi **Wokwi: Start Simulator** để bỏ cấu hình cũ của phiên Wokwi. Kiểm tra Serial `outputs=ENABLED` và HA “Đầu ra motor: Đã bật đầu ra”. Sơ đồ Wokwi có công tắc trượt dừng khẩn (trái = bình thường, phải = lỗi), nút driver fault, hai công tắc trượt hành trình (trái = chưa chạm, phải = đã chạm) và ba LED IN1/IN2/EN. Không nạp bản Wokwi lên motor thật chưa nghiệm thu.

Bản Wokwi tự mô phỏng hành trình: để cả **LIMIT OPEN / LIMIT CLOSE bên trái**, chọn AUTO một lần. Khi tới đích, motor dừng và AUTO vẫn bật; có mưa liên tục 500 ms sẽ tự đóng, hết mưa và đủ điều kiện an toàn 10 giây sẽ mở lại. Một hành trình đầy đủ mất 5 giây theo đồng hồ ESP32 (thời gian thực có thể dài hơn nếu mô phỏng chạy chậm). Công tắc thủ công vẫn cho phép ép vị trí để thử; hai công tắc cùng bật vẫn chốt lỗi. Dừng khẩn, driver fault và bảo vệ timeout vẫn hoạt động. Nếu đang dùng phiên firmware cũ bị `MOTION_TIMEOUT`, build lại và dừng/chạy lại Wokwi rồi chọn AUTO. Với phần cứng thật, phải kiểm tra motor/công tắc khi timeout, nhấn **Xóa lỗi** rồi chọn lại chế độ; không tự xóa lỗi để thử chạy lại. Mở thủ công vẫn cần khô, sáng, DHT hợp lệ và độ ẩm dưới 70% liên tục 10 giây. Firmware và dashboard hiển thị riêng lỗi quá thời gian, dừng khẩn, hai hành trình, driver và điều kiện mở.

Host tests không kiểm chứng GPIO, độ trễ scheduler, dòng motor hoặc dịch vụ cloud. Cần nghiệm thu thực tế: chiều quay, công tắc đúng đầu, hai công tắc cùng active, dừng khẩn và đứt dây NC, driver fault, kẹt/quá thời gian, mất Wi-Fi, mất nguồn rồi khởi động lại. Từ khóa lỗi: `ESTOP`, `BOTH_LIMITS`, `DRIVER_FAULT`, `MOTION_TIMEOUT`.

## Tài liệu tham khảo

- [Node-RED HTTP endpoint](https://cookbook.nodered.org/http/create-an-http-endpoint)
- [Node-RED Function nodes](https://nodered.org/docs/user-guide/writing-functions)
- [Wokwi slide switch](https://docs.wokwi.com/parts/wokwi-slide-switch)
