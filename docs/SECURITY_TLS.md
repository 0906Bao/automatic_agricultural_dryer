# MQTT TLS, sequence và bảo trì bảo mật

## Kết nối hiện tại

MQTT chỉ dùng TLS trên cổng **8883**, tối thiểu TLS 1.2. Cổng 1883 không còn listener hoặc Docker port mapping. Bind vẫn giới hạn localhost và địa chỉ host VMnet8 `192.168.137.1`; firewall chặn nguồn ngoài mạng được phép. Tài khoản và ACL từ Priority 1 được giữ nguyên.

- ESP32 dùng `WiFiClientSecure`, `setCACert()` và hostname `MQTT_HOST`. CA public được provision vào `include/mqtt_ca.local.h`, Git bỏ qua. Thiếu CA hoặc đồng hồ chưa đồng bộ SNTP thì MQTT không kết nối; không có `setInsecure()` hoặc fallback plaintext. Motor safety task vẫn hoạt động độc lập khi mạng lỗi.
- Mọi broker node Node-RED dùng TLS config `dryer-mqtt-tls`, CA `/run/dryer/ca.crt`, `verifyservercert=true`, server name `mosquitto`.
- Home Assistant MQTT integration dùng `192.168.137.1:8883`, CA riêng được upload qua API cấu hình và `tls_insecure=false`.
- CA có SAN cho các tên broker nội bộ/Wokwi và các IP host đang dùng. Khi chuyển sang máy/IP khác phải cấp lại chứng thư có SAN đúng; không tắt xác minh để xử lý lỗi hostname.

Khóa CA ở `.local/security/pki/ca.key` không được mount vào container. Broker chỉ nhận thư mục `pki/server`; Node-RED chỉ nhận CA public. Thư mục `.local/security` đã hạn chế quyền NTFS. Chứng thư broker có hạn 397 ngày; hạn cụ thể và fingerprint CA nằm trong `.local/security/tls-migration.json`.

## Sequence

Firmware chỉ chấp nhận sequence tăng trong cửa sổ tối đa **64**, phạm vi 32 bit. Gói có số cực lớn bị từ chối trước khi thay đổi bộ đếm. Node-RED không dùng timestamp làm sequence; HTTP và HA chia sẻ bộ đếm đặt chỗ theo session, bám sequence đã được ESP32 xác nhận. Bộ đếm cục bộ bị hỏng hoặc thuộc session cũ không được đẩy xuống thiết bị.

ESP32 đổi session và đặt lại bộ đếm trước khi tới giới hạn, sau khi xuất telemetry xác nhận lệnh cuối của session cũ. Gói mang session cũ hoặc sequence trùng bị từ chối; không tự gửi lại lệnh chuyển động khi timeout. Lệnh đã qua gate nhưng bị interlock từ chối vẫn tiêu thụ sequence để không phát lại về sau. Tài khoản có quyền gửi lệnh vẫn cần được bảo vệ; cơ chế này không thay thế ACL hoặc dừng khẩn vật lý.

## Kiểm tra

```powershell
python tools/harden-tls.py verify
python tools/harden-tls.py verify_commands
powershell -NoProfile -ExecutionPolicy Bypass -File test/run-host.ps1
```

`verify` kiểm tra CA/hostname, cổng plaintext đóng, tài khoản/ACL, telemetry và flow runtime khớp snapshot đã triển khai. `verify_commands` chỉ chạy khi motor đang idle: gửi sequence quá lớn với STOP, xác nhận bộ đếm không đổi, gửi STOP kế tiếp và kiểm tra duplicate bị chặn. Nó còn thử một lần đăng nhập sai để kiểm tra audit log. Không dùng các lệnh này khi đang vận hành motor thật.

Các bài smoke cũ tạo topic tạm chưa được cấp quyền trong ACL production; không mở ACL rộng để chạy chúng. Dùng bộ kiểm tra TLS mới hoặc một broker test riêng.

## Log và phát hiện bất thường

- Mosquitto bật log kết nối, TLS, đăng nhập lỗi và ACL bị từ chối. Debug log ghi topic/kích thước, không ghi payload MQTT.
- Node-RED bật audit log; `command_rejected` ghi lý do và lệnh đã chuẩn hóa, không ghi token, credentials hoặc payload đầu vào.
- ESP32 ghi lý do từ chối qua Serial; trạng thái từ chối hợp lệ trên `dryer/status` được bridge ghi vào log Node-RED, gộp cùng lý do trong 5 giây để hạn chế nhiễu.
- Docker giữ tối đa 5 tệp × 10 MB cho mỗi dịch vụ, tránh log chiếm hết ổ đĩa.

```powershell
docker compose logs --since 1h node-red mosquitto
```

Tìm `command_rejected`, `auth.login`, `not authorised`, `Denied PUBLISH` và các lỗi TLS. Không chia sẻ log thô nếu chưa kiểm tra thông tin người dùng/client ID.

## Phụ thuộc và cập nhật

Compose ghim Node-RED 5.0.8 và Mosquitto 2.1.2 bằng cả tag lẫn digest của image đã có. PlatformIO ghim nền tảng espressif32 7.1.3, PubSubClient 2.8.0 và DHTesp 1.19.0. Các thư viện Python dùng cho bảo mật/chẩn đoán được ghim trong `requirements-security.txt`. Ghim phiên bản bảo đảm tái lập, không chứng minh phiên bản không có lỗ hổng.

Đã tạo lịch Codex kiểm tra nguồn chính thức, dấu hiệu bất thường và hạn chứng thư vào 09:00 thứ Hai hằng tuần, giờ Việt Nam. Lần kiểm tra định kỳ không tự khởi động lại/flash thiết bị. `.github/dependabot.yml` cũng đặt lịch tuần cho Docker Compose và GitHub Actions; phần Dependabot chỉ có hiệu lực khi cấu hình được commit/push lên nhánh mặc định.

Khi nâng cấp: sao lưu, cập nhật tag/digest/phiên bản, chạy host tests và build cả `esp32dev`/`wokwi`, kiểm tra TLS/ACL/sequence, rồi triển khai trong đợt bảo trì. Với chứng thư còn dưới 30 ngày: cấp leaf certificate mới từ cùng CA, giữ SAN, SKI/AKI và serverAuth đúng, kiểm tra bằng OpenSSL/Python strict, reload broker bằng SIGHUP. Không cần thay firmware nếu CA không đổi. Nếu đổi CA, phải đồng bộ CA cho firmware, Node-RED và HA trước khi gỡ CA cũ.

## Backup

`tls-migration.json` ghi vị trí backup trước TLS, bao gồm flow/data Node-RED, cấu hình và firmware Wokwi trước chuyển đổi. Tệp `.local/security/tls-expected-flows.json` là snapshot runtime sau cập nhật. Bảo vệ mọi backup như credentials. Không phục hồi cấu hình cũ rồi mở lại cổng plaintext ra mạng.
