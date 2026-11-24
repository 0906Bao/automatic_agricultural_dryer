# Kết quả xác minh Home Assistant

Phiên triển khai ngày 23/11/2026, múi giờ người dùng Asia/Saigon. Chỉ các kết quả có thực thi bên dưới được ghi là đã đạt.

## Kiểm tra trực tiếp Wokwi, Node-RED và Home Assistant sau phản ánh lỗi nút

- Nguyên nhân: phiên Wokwi giữ cấu hình/binary cũ, telemetry báo `motor_output_enabled=false`; thiếu hành trình đích gây `MOTION_TIMEOUT` sau 20 giây ESP32, chốt lỗi và chuyển `STOPPED`. Vì vậy AUTO tắt và OPEN/CLOSE bị từ chối. Đã reload cửa sổ VS Code, mở lại Wokwi với `.pio/build/wokwi/firmware.bin`; Serial và MQTT xác nhận đầu ra bật.
- Đã gửi nút HA thật qua bridge Node-RED tới ESP32 Wokwi, không dùng ACK emulator: CLOSE → `MANUAL_CLOSE/CLOSING/motor_active=true`; OPEN → `MANUAL_OPEN/OPENING/motor_active=true`; STOP → `STOPPED/motor_active=false`; RESET và AUTO được firmware xác nhận `ACCEPTED`. Nút MANUAL cũng xác nhận `ACCEPTED`, đưa về STOPPED; bật AUTO lại thành công khi hành trình mở vẫn đang kích hoạt.
- Hai hành trình Wokwi đổi sang công tắc trượt giữ trạng thái: trái = nhả, phải = chạm. GPIO18 vẫn đóng, GPIO19 vẫn mở, common vào GPIO và tiếp điểm phải nối GND. Đã quan sát AUTO đang mở, gạt LIMIT OPEN sang phải → `IDLE`, giữ `AUTO`, `fault=NONE`. Theo dõi thêm 70 giây thời gian thực vẫn AUTO, không cấp motor. Không giả lập vị trí bằng yêu cầu OPEN/CLOSE, không bỏ bảo vệ timeout.
- HA cuối phép thử xác nhận `cover.dryer_roof=open`, vị trí “Đã mở hoàn toàn”, limit_open ON/limit_closed OFF, motor output ON/motor active OFF, AUTO “Đang bật”.
- Dashboard đã sao lưu, `ha core check` và reload thành công; hiển thị hướng dẫn công tắc mới, giải thích AUTO dừng khi quá thời gian. Firmware phản hồi riêng lỗi timeout, dừng khẩn, hai hành trình, driver và điều kiện mở chưa đủ.
- Kiểm tra sau deploy: MQTT integration `loaded`, đủ 14 entity gốc, 37 tham chiếu dashboard hợp lệ, 5 node cũ giữ nguyên, không còn entity thử, HTTP localhost/LAN đều 200. Quan sát 35 giây nhận 12 telemetry và 12 HA state, khoảng cách lớn nhất khoảng 5,26 giây; không bảo đảm mọi phiên mạng sau này đều không gián đoạn.
- Cả `esp32dev` và `wokwi` build SUCCESS. 100.083 assertion C++ và 16 bài Node.js PASS, gồm hồi quy timeout/chốt lỗi và đấu dây hai hành trình. Kết quả chạy ghi ở `.local/live-movement.json`, `.local/live-auto.json`, `.local/live-final-status.json` (không đưa vào Git).

Đây là kiểm tra ESP32 mô phỏng, chưa nghiệm thu motor/driver thật. Các kết quả emulator/namespace riêng ở phần dưới là kiểm tra bổ sung trước đó.

## Môi trường thực tế

- HAOS 18.4 trên VMware Workstation 17.5.2, Core 2026.11.2, Supervisor 2026.11.0. `ha info` báo `supported: true`.
- VM NAT: 192.168.137.50; Core HTTP 80, gateway Windows 8123. Không triển khai Home Assistant Container hoặc Supervised trên Docker Desktop.
- Broker hiện có `iot-mosquitto`, Node-RED `iot-node-red`; thêm riêng `iot-ha-access`. Không tạo broker thứ hai.
- Network/volume của project `automatic_agricultural_dryer` được giữ nguyên, không chạy down -v hoặc xóa volume/container cũ.
- Đã sao lưu Node-RED `/data`, cấu hình broker và flow trước khi merge bridge trong `backups/` (bị Git bỏ qua).

## Các kiểm tra đã chạy và quan sát

| Kiểm tra | Kết quả |
| --- | --- |
| `pio run -e esp32dev` | SUCCESS; RAM 13,9%, Flash 61,0% |
| `test/run-host.ps1` | PASS: 100.083 assertion C++ trên lớp production; 16 bài Node.js sau cập nhật hành trình Wokwi |
| `python tools/build-home-assistant.py --check` | PASS |
| `node tools/build-flow.cjs --check` | PASS |
| Compose gốc, Compose phụ, overlay MQTT secure | `config --quiet` hợp lệ; secure overlay chưa được bật |
| `ha core check` trên VM thật | Command completed successfully |
| MQTT integration Home Assistant | loaded, kết nối broker Windows VMnet8; không cài Mosquitto app |
| Entities theo yêu cầu | Đủ 14 entity ID; tổng 41 state gồm entities/scripts/automations của project |
| Dashboard | Nạp qua API Lovelace; cả 32 tham chiếu entity đều tồn tại |
| Giữ flow Node-RED | So sánh nội dung 5 node ban đầu với backup: bằng nhau, không chỉ so số lượng |
| localhost HTTP | `http://localhost:8123` trả 200 |
| LAN HTTP từ Windows host | `http://192.168.1.4:8123` trả 200 |
| Firewall | Rule Agricultural Dryer HA LAN, chỉ TCP8123, RemoteAddress LocalSubnet; không tắt firewall/đổi Wi-Fi profile/forward Internet |
| Kiểm thử tích hợp riêng | 16 kiểm tra live qua broker, Node-RED và HAOS thật đã qua |
| Dọn thử nghiệm | Tab, package và 33 entity-registry entry của mỗi lượt thử được dọn bằng API; audit cuối không còn test state/node |

Kết quả kỹ thuật không chứa secrets ở `.local/ha-runtime-test-result.json` và `.local/ha-final-verification.json`. Thư mục `.local` không được commit vì còn chứa khóa SSH và cấu hình theo máy.

### Giới hạn của kiểm thử live

`tools/test-ha-runtime.py` phát telemetry/ACK **giả lập** qua namespace riêng `dryertest/<timestamp>/`, tạo package/entity `dryer_smoke_<timestamp>_*` và tab Node-RED tạm. Không phát lệnh hoặc dữ liệu thử vào `dryer/command`/`dryer/telemetry` thật. Broker, Node-RED, MQTT integration, template cover và Home Assistant Core trong phép thử là dịch vụ thật. Không có ESP32, ADC, DHT, motor thật tham gia phép thử này.

16 kiểm tra live gồm: nhận nhiệt độ; đổi nhiệt độ; cảnh báo RH75; nguy hiểm RH85/yêu cầu đóng hiển thị; mưa; tối; DHT invalid không hiển thị số cũ; button CLOSE qua envelope/ACK emulator; cover OPEN và phản hồi từ chối emulator; closed limit; open limit; cả hai OFF → unknown; cả hai ON → fault/unknown; telemetry stale → offline; có dữ liệu trở lại; **restart Core thật và tự nhận dữ liệu MQTT mới trở lại**.

Các assertion C++ chạy trực tiếp header production, với thời gian/đầu vào do test điều khiển, xác nhận interlock 30 giây và bộ điều khiển motor. Chúng không đo thời gian thực, dòng kẹt, độ trễ GPIO hoặc độ tin cậy phần cứng.

## Ma trận 14 tình huống của yêu cầu

| STT | Tình huống | Bằng chứng / trạng thái |
| --- | --- | --- |
| 1 | ESP32 gửi telemetry, HA nhận | Đạt luồng thật với publisher giả lập; chưa chạy ESP32/Wokwi thật |
| 2 | Nhiệt độ thay đổi | Đã quan sát HA đổi 30 → 36 qua MQTT/Node-RED |
| 3 | Độ ẩm 75% | Đã quan sát humidity_warning ON trong HA; dữ liệu giả lập |
| 4 | Độ ẩm 85% | Đã quan sát humidity_danger ON và CLOSE hiển thị; logic đóng firmware được kiểm tra bằng C++; chưa sensor/motor thật |
| 5 | Rain ADC >=2200 | Đã quan sát ADC2300/rain ON qua fixture; đọc ADC/chân thật chưa xác minh |
| 6 | LDR tối | Đã quan sát dark ON qua fixture; chuyển lux/hysteresis trên Wokwi chưa xác minh |
| 7 | An toàn đủ 30 giây mới mở | C++ production: từ chối trước mốc30 giây, cho phép đúng mốc và reset timer khi điều kiện gián đoạn; chưa đo trên board thật |
| 8 | DHT22 lỗi | HA hiển thị temperature unavailable/dht_valid OFF, không dùng -999; C++ kiểm tra interlock; chưa rút cảm biến thật |
| 9 | CLOSE từ HA | Đã chạy MQTT Button → Node-RED → envelope → ACK emulator; chưa xác nhận ESP32 nhận |
| 10 | OPEN khi mưa | Đã quan sát phản hồi REJECTED từ emulator; interlock firmware có host test; chưa thử ESP32 thật |
| 11 | Limit đóng | Fixture kích hoạt limit_closed, cover chuyển closed; chưa nhấn công tắc thật |
| 12 | Limit mở | Fixture kích hoạt limit_open, cover chuyển open; chưa nhấn công tắc thật |
| 13 | ESP32 mất kết nối | Đã ngừng publisher và quan sát HA offline sau freshness timeout; chưa cắt điện ESP32 thật |
| 14 | HA restart | Đã restart Core thật, MQTT kết nối lại và nhiệt độ31 cập nhật từ publisher đang chạy |

Cảnh báo persistent notification đã được cấu hình và load vào HA, nhưng phép thử namespace riêng không bật automation cảnh báo để tránh tạo cảnh báo giả trên hệ thống chính. Chưa xác minh push notification/Companion App hoặc giao diện trên điện thoại thật. Trang frontend được kiểm tra HTTP/API, chưa nghiệm thu bố cục bằng người dùng trên điện thoại.

## Việc còn cần trên thiết bị của người dùng

Cập nhật Việt hóa/chế độ tự động: đã triển khai các sensor hiển thị tiếng Việt và ô chế độ đầu trang. 18 kiểm tra tích hợp namespace riêng đã qua, gồm telemetry AUTO → Đang bật, STOPPED/thủ công → Đang tắt, nhấn AUTO và nhận ACK nhưng mode chưa đổi vẫn giữ tắt, mất telemetry → Chưa xác nhận/auto_enabled unavailable. Kiểm tra sau deploy: 14 entity gốc đủ, 36 tham chiếu dashboard hợp lệ, 5 node cũ giữ nguyên, không còn state thử nghiệm; template ô chế độ render từ dữ liệu thật thành **TỰ ĐỘNG ĐANG TẮT**. Các nút thử chỉ tác động namespace mô phỏng, không gửi yêu cầu AUTO vào thiết bị thật.

Cập nhật chẩn đoán Unknown/Unavailable sau bàn giao: log broker ghi nhận ESP32 bị ngắt vì keepalive timeout; đo MQTT trong35 giây thấy7 gói telemetry, khoảng cách lớn nhất7,566 giây, cả hai limit false và motor_output_enabled false. Đã cập nhật nhãn vị trí tiếng Việt, giữ cover unknown khi chưa có hành trình, giữ ngưỡng stale10 giây và bổ sung thông báo đầu ra motor đang khóa. 15 kiểm tra live với publisher riêng (không restart Core) đã qua, bao gồm4 trường hợp hành trình và mất dữ liệu/offline. Firmware mới build qua, đổi telemetry2500→1000ms và cho reconnect khi đầu ra motor khóa; tần suất trên Wokwi đang chạy chỉ thay đổi sau khi restart/nạp bản mới. Không khẳng định đã loại bỏ mọi timeout mạng.

1. Đăng nhập `dryer-admin` bằng mật khẩu lưu trong `%LOCALAPPDATA%\AutomaticAgriculturalDryer\HAOS\access.json`; đổi mật khẩu theo nhu cầu, không chia sẻ file có token.
2. Chạy Wokwi hoặc nạp firmware vừa build vào đúng ESP32. Không mở khóa motor thật khi chưa nghiệm thu driver/nguồn/hành trình/dừng khẩn.
3. Kiểm tra toàn bộ 14 tình huống trên mô phỏng/phần cứng thật, đặc biệt các mốc ADC, 30 giây, lỗi cảm biến.
4. Trên điện thoại cùng LAN, mở URL LAN/đăng nhập Companion App, kiểm tra cảnh báo. HTTP200 từ host không thay thế kiểm tra bằng điện thoại.
5. Chuyển MQTT sang xác thực/ACL theo lịch bảo trì trước khi sử dụng thực tế; anonymous hiện tại chỉ dành cho lab và chưa được âm thầm thay đổi.
6. Cấu hình autostart VMware sau reboot nếu muốn chạy liên tục; gateway đã có restart unless-stopped nhưng VM không tự bật theo Docker.
