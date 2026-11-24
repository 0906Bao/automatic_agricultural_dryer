"""Generate non-secret Home Assistant package/dashboard; requires PyYAML."""
from pathlib import Path
import argparse
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "home-assistant"

NAMES = {
    "temperature":"Nhiệt độ", "humidity":"Độ ẩm", "rain_adc":"Giá trị cảm biến mưa",
    "light_adc":"Giá trị cảm biến ánh sáng", "rain":"Mưa", "dark":"Trời tối",
    "humidity_warning":"Cảnh báo độ ẩm cao", "humidity_danger":"Độ ẩm nguy hiểm",
    "dht_valid":"Cảm biến nhiệt độ và độ ẩm", "limit_closed":"Hành trình đóng",
    "limit_open":"Hành trình mở", "limit_fault":"Lỗi hành trình", "safe_to_open":"Điều kiện mở bạt",
    "estop":"Dừng khẩn", "driver_fault":"Lỗi bộ điều khiển motor",
    "motor_output_enabled":"Đầu ra motor", "motor_active":"Hoạt động motor",
    "cover_request":"Đề xuất theo thời tiết", "cover_reason":"Nguyên nhân đề xuất",
    "mode":"Chế độ điều khiển", "motion":"Lệnh chuyển động", "fault":"Tình trạng lỗi",
    "roof_position":"Vị trí bạt", "command_result":"Kết quả yêu cầu gần nhất", "online":"Kết nối thiết bị",
}

def entity(domain, key, field=None, **kwargs):
    result = {"name": NAMES.get(key, key),
              "unique_id": f"dryer_{key}", "default_entity_id": f"{domain}.dryer_{key}",
              "state_topic": "dryer/ha/state", "availability_topic": "dryer/ha/availability",
              "expire_after": 12,
              "value_template": "{{ value_json." + (field or key) + " }}"}
    result.update(kwargs)
    return result

sensors = [
    entity("sensor", "temperature", "temperature_c", device_class="temperature", unit_of_measurement="°C", state_class="measurement"),
    entity("sensor", "humidity", "humidity_pct", device_class="humidity", unit_of_measurement="%", state_class="measurement"),
    entity("sensor", "rain_adc", state_class="measurement"),
    entity("sensor", "light_adc", state_class="measurement"),
    *[entity("sensor", key) for key in ["cover_request", "cover_reason", "mode", "motion", "fault", "roof_position"]],
]
for item in sensors:
    if item["unique_id"] == "dryer_roof_position":
        item["value_template"] = "{{ {'open': 'Đã mở hoàn toàn', 'closed': 'Đã đóng hoàn toàn', 'unknown': 'Chưa chạm hành trình', 'FAULT': 'Lỗi hai công tắc'}.get(value_json.roof_position, 'Dữ liệu vị trí không hợp lệ') }}"
for item in sensors[:2]:
    item.pop("availability_topic")
    item["availability_mode"] = "all"
    item["availability"] = [
        {"topic": "dryer/ha/availability"},
        {"topic": "dryer/ha/state", "value_template": "{{ 'online' if value_json.dht_valid else 'offline' }}"}]

command_sensor = entity("sensor", "command_result", value_template="{{ value_json.result }}", state_topic="dryer/ha/command_result")
command_sensor.pop("expire_after") # explicitly the LAST result, not a live sensor measurement
command_sensor["json_attributes_topic"] = "dryer/ha/command_result"
sensors.append(command_sensor)

binary = []
for key, field in [("rain","rain"),("dark","dark"),("humidity_warning","humidity_warning"),
                   ("humidity_danger","humidity_danger"),("dht_valid","dht_valid"),
                   ("limit_closed","limit_covered"),("limit_open","limit_open"),
                   ("limit_fault","limit_fault"),("safe_to_open","safe_to_open"),
                   ("estop","estop"),("driver_fault","driver_fault"),
                   ("motor_output_enabled","motor_output_enabled"),("motor_active","motor_active")]:
    binary.append(entity("binary_sensor", key, field, payload_on="ON", payload_off="OFF",
                         value_template="{{ 'ON' if value_json."+field+" else 'OFF' }}"))
binary.append({"name":NAMES["online"],"unique_id":"dryer_online","default_entity_id":"binary_sensor.dryer_online",
               "device_class":"connectivity","state_topic":"dryer/ha/heartbeat",
               "payload_on":"online","payload_off":"offline","expire_after":6})

buttons = []
for cmd in ["OPEN","CLOSE","AUTO","MANUAL","STOP","RESET"]:
    buttons.append({"name":{"OPEN":"Mở bạt","CLOSE":"Đóng bạt","AUTO":"Bật tự động","MANUAL":"Chuyển thủ công và dừng","STOP":"Dừng bạt","RESET":"Xóa lỗi"}[cmd],"unique_id":f"dryer_{cmd.lower()}",
                    "default_entity_id":f"button.dryer_{cmd.lower()}","command_topic":"dryer/ha/command",
                    "availability_topic":"dryer/ha/availability","qos":0,"retain":False,"payload_press":cmd,
                    "command_template":"{{ {'command': value, 'issued_at': (as_timestamp(now()) * 1000) | int} | to_json }}"})

def notification(identifier, title, message, triggers, **extra):
    return {"id":f"dryer_{identifier}","alias":f"Giàn phơi - {title}","mode":"single",
            "triggers":triggers,
            "actions":[{"action":"persistent_notification.create","data":{
                "notification_id":f"dryer_{identifier}","title":title,"message":message}}], **extra}

alerts = []
for key,title,text in [
    ("rain","Phát hiện mưa","ESP32 phát hiện mưa. Chế độ AUTO sẽ yêu cầu che bạt; kiểm tra hành trình để biết vị trí thực tế."),
    ("humidity_warning","Độ ẩm cao","Độ ẩm từ 70% trở lên. Chưa đủ điều kiện mở bạt; theo dõi hiệu quả phơi."),
    ("humidity_danger","Độ ẩm nguy hiểm","Độ ẩm trên 80%. ESP32 cấm mở và AUTO yêu cầu che bạt."),
    ("limit_fault","Lỗi công tắc hành trình","Hai công tắc đóng và mở cùng kích hoạt. ESP32 chốt lỗi, cần kiểm tra đấu dây và cơ khí trước RESET.")]:
    alerts.append(notification(key,title,text,[{"trigger":"state","entity_id":f"binary_sensor.dryer_{key}","to":"on"}]))
alerts += [
    notification("dht_error","Lỗi DHT22","Số đo DHT22 không hợp lệ. Không dùng số đo cuối làm dữ liệu hiện tại; ESP32 cấm mở.",
                 [{"trigger":"state","entity_id":"binary_sensor.dryer_dht_valid","to":"off"}]),
    notification("offline","Giàn phơi mất kết nối","Không có telemetry mới hoặc bridge MQTT/Node-RED mất kết nối. Không thể xác nhận vị trí; dùng dừng khẩn vật lý nếu cần.",
                 [{"trigger":"state","entity_id":"binary_sensor.dryer_online","to":"off","for":"00:00:10"},
                  {"trigger":"state","entity_id":"binary_sensor.dryer_online","to":"unavailable","for":"00:00:10"}]),
    notification("command_failed","Yêu cầu điều khiển chưa được thực hiện",
                 "Lệnh {{ state_attr('sensor.dryer_command_result','command') }}: {{ states('sensor.dryer_command_result') }}. Mở bạt cần khô, sáng, DHT hợp lệ và độ ẩm dưới 70% liên tục 30 giây; kiểm tra dừng khẩn và lỗi hành trình. TIMEOUT nghĩa là chưa có xác nhận, không tự gửi lại.",
                 [{"trigger":"state","entity_id":"sensor.dryer_command_result"}],
                 conditions=[{"condition":"template","value_template":"{{ states('sensor.dryer_command_result').startswith('REJECTED') or states('sensor.dryer_command_result') in ['TIMEOUT','DEVICE_RESTARTED','SUPERSEDED'] }}"}]),
]

package = {
    "mqtt":{"sensor":sensors,"binary_sensor":binary,"button":buttons},
    "script":{"dryer_send_command":{"alias":"Dryer - gửi yêu cầu điều khiển","mode":"parallel","max":5,
        "fields":{"command":{"required":True,"selector":{"select":{"options":["OPEN","CLOSE","AUTO","MANUAL","STOP","RESET"]}}}},
        "sequence":[{"condition":"template","value_template":"{{ command in ['OPEN','CLOSE','AUTO','MANUAL','STOP','RESET'] }}"},
                    {"action":"mqtt.publish","data":{"topic":"dryer/ha/command","qos":0,"retain":False,
                     "payload":"{{ {'command': command, 'issued_at': (as_timestamp(now()) * 1000) | int} | to_json }}"}}]}},
    "template":[{"cover":[{"name":"Mái che giàn phơi","unique_id":"dryer_roof","default_entity_id":"cover.dryer_roof",
        "device_class":"awning","optimistic":False,
        "availability":"{{ is_state('binary_sensor.dryer_online','on') and has_value('binary_sensor.dryer_limit_closed') and has_value('binary_sensor.dryer_limit_open') }}",
        "state":"{% if is_state('binary_sensor.dryer_limit_closed','on') and is_state('binary_sensor.dryer_limit_open','off') %}closed{% elif is_state('binary_sensor.dryer_limit_open','on') and is_state('binary_sensor.dryer_limit_closed','off') %}open{% else %}{{ none }}{% endif %}",
        "open_cover":[{"action":"script.dryer_send_command","data":{"command":"OPEN"}}],
        "close_cover":[{"action":"script.dryer_send_command","data":{"command":"CLOSE"}}],
        "stop_cover":[{"action":"script.dryer_send_command","data":{"command":"STOP"}}]}]}],
    "automation":alerts,
}

# Keep raw MQTT states/IDs unchanged for firmware, history and existing automations.
# Presentation sensors translate states only; controls still use the ESP32 state.
TEXT_VALUES = {
    "mode":{"AUTO":"Tự động", "STOPPED":"Đang dừng", "MANUAL_OPEN":"Thủ công: mở bạt", "MANUAL_CLOSE":"Thủ công: đóng bạt"},
    "motion":{"IDLE":"Đứng yên", "OPENING":"Yêu cầu mở bạt", "CLOSING":"Yêu cầu đóng bạt", "REVERSAL_WAIT":"Chờ đổi chiều", "FAULT":"Dừng do lỗi"},
    "fault":{"NONE":"Không có lỗi", "ESTOP":"Đã kích hoạt dừng khẩn", "BOTH_LIMITS":"Hai hành trình cùng bật", "MOTION_TIMEOUT":"Quá thời gian di chuyển", "DRIVER_FAULT":"Bộ điều khiển motor báo lỗi"},
    "cover_request":{"OPEN":"Mở bạt", "CLOSE":"Đóng bạt"},
    "cover_reason":{"NORMAL":"Điều kiện bình thường", "RAIN":"Có mưa", "DARK":"Trời tối", "DHT_ERROR":"Lỗi cảm biến nhiệt độ/độ ẩm", "HUMIDITY_WARNING":"Độ ẩm cao", "HUMIDITY_DANGER":"Độ ẩm nguy hiểm"},
    "command_result":{"PENDING":"Đang chờ thiết bị xác nhận", "ACCEPTED":"Đã nhận yêu cầu", "REJECTED_INTERLOCK_OR_COMMAND":"Từ chối: chưa đủ điều kiện an toàn hoặc đang có lỗi", "REJECTED_OFFLINE":"Từ chối: thiếu dữ liệu mới", "REJECTED_EXPIRED":"Từ chối: yêu cầu đã hết hạn", "REJECTED_RATE_LIMIT":"Gửi quá nhanh, vui lòng chờ", "REJECTED_BUSY":"Đang chờ yêu cầu trước", "REJECTED_COMMAND":"Yêu cầu không hợp lệ", "REJECTED_RETAINED":"Từ chối yêu cầu lưu cũ", "REJECTED_SEQUENCE":"Mã yêu cầu không hợp lệ", "TIMEOUT":"Chưa nhận được xác nhận", "DEVICE_RESTARTED":"Thiết bị đã khởi động lại", "SUPERSEDED":"Đã có yêu cầu mới hơn"},
    "online":{"on":"Đã kết nối", "off":"Mất kết nối", "unknown":"Chưa có dữ liệu", "unavailable":"Mất kết nối"},
    "rain":{"on":"Có mưa", "off":"Không mưa"}, "dark":{"on":"Trời tối", "off":"Trời sáng"},
    "dht_valid":{"on":"Hoạt động bình thường", "off":"Cảm biến báo lỗi"},
    "safe_to_open":{"on":"Đủ điều kiện mở bạt", "off":"Chưa đủ điều kiện mở bạt"},
    "limit_closed":{"on":"Đã tới vị trí đóng", "off":"Chưa kích hoạt"},
    "limit_open":{"on":"Đã tới vị trí mở", "off":"Chưa kích hoạt"},
    "limit_fault":{"on":"Hai hành trình cùng bật", "off":"Không có lỗi"},
    "estop":{"on":"Đang dừng khẩn", "off":"Không kích hoạt"},
    "driver_fault":{"on":"Có lỗi bộ điều khiển", "off":"Không có lỗi"},
    "motor_output_enabled":{"on":"Đã bật đầu ra", "off":"Đang khóa đầu ra"},
    "motor_active":{"on":"Đang cấp lệnh chạy", "off":"Đang dừng"},
    "humidity_warning":{"on":"Độ ẩm cao từ 70%", "off":"Không có cảnh báo"},
    "humidity_danger":{"on":"Độ ẩm nguy hiểm trên 80%", "off":"Không có cảnh báo"},
}
TEXT_VALUES["command_result"].update({
    "REJECTED_MOTION_TIMEOUT":"Quá 20 giây chưa chạm hành trình. Kiểm tra rồi nhấn Xóa lỗi",
    "REJECTED_ESTOP":"Từ chối: dừng khẩn đang kích hoạt",
    "REJECTED_BOTH_LIMITS":"Từ chối: hai hành trình cùng kích hoạt",
    "REJECTED_DRIVER_FAULT":"Từ chối: bộ điều khiển motor báo lỗi",
    "REJECTED_OPEN_UNSAFE":"Chưa thể mở: cần khô, sáng, DHT tốt, độ ẩm dưới 70% liên tục 30 giây",
    "REJECTED_TASK_UNAVAILABLE":"Từ chối: tác vụ điều khiển motor chưa sẵn sàng",
})
raw_binary={item["unique_id"].removeprefix("dryer_") for item in binary}
display=[]
for key in [*TEXT_VALUES, "rain_adc", "light_adc", "roof_position"]:
    domain="binary_sensor" if key in raw_binary else "sensor"
    source=f"{domain}.dryer_{key}"
    mapping=repr(TEXT_VALUES.get(key,{}))
    fallback="value" if key in ["rain_adc","light_adc","roof_position"] else "'Chưa có dữ liệu'"
    state="{% set value = states('"+source+"') %}"
    if key!="online":
        state+="{% if not is_state('binary_sensor.dryer_online','on') %}Mất kết nối{% elif value in ['unknown','unavailable'] %}Chưa có dữ liệu{% else %}{{ "+mapping+".get(value, "+fallback+") }}{% endif %}"
    else: state+="{{ "+mapping+".get(value, 'Chưa có dữ liệu') }}"
    display.append({"name":NAMES[key],"unique_id":f"dryer_{key}_text","default_entity_id":f"sensor.dryer_{key}_text","state":state})

AUTO_STATE="{% if not is_state('binary_sensor.dryer_online','on') or not has_value('sensor.dryer_mode') %}Chưa xác nhận{% elif is_state('sensor.dryer_mode','AUTO') %}Đang bật{% else %}Đang tắt{% endif %}"
display.append({"name":"Chế độ tự động","unique_id":"dryer_auto_status","default_entity_id":"sensor.dryer_auto_status","state":AUTO_STATE})
package["template"].append({"sensor":display,"binary_sensor":[{
    "name":"Tự động đang bật","unique_id":"dryer_auto_enabled","default_entity_id":"binary_sensor.dryer_auto_enabled",
    "availability":"{{ is_state('binary_sensor.dryer_online','on') and has_value('sensor.dryer_mode') }}",
    "state":"{{ is_state('sensor.dryer_mode','AUTO') }}","icon":"mdi:autorenew"}]})

AUTO_BANNER="""{% if not is_state('binary_sensor.dryer_online','on') or not has_value('sensor.dryer_mode') %}
## ⚪ CHƯA XÁC NHẬN CHẾ ĐỘ
Thiếu dữ liệu mới từ thiết bị. Không thể xác nhận tự động đang bật hay tắt.
{% elif is_state('sensor.dryer_mode','AUTO') %}
## 🟢 TỰ ĐỘNG ĐANG BẬT
Thiết bị đã xác nhận chế độ tự động. Bạt sẽ được yêu cầu đóng/mở theo thời tiết và các điều kiện an toàn.
{% elif is_state('sensor.dryer_mode','STOPPED') %}
## ⏸️ TỰ ĐỘNG ĐANG TẮT
{% if is_state('sensor.dryer_fault','MOTION_TIMEOUT') %}
**Đã dừng do quá thời gian:** chưa chạm hành trình trong 20 giây. Trong Wokwi, gạt LIMIT OPEN hoặc LIMIT CLOSE sang phải để xác nhận hành trình đích. Sau khi kiểm tra, nhấn **Xóa lỗi**, rồi chọn lại chế độ.
{% elif has_value('sensor.dryer_fault') and not is_state('sensor.dryer_fault','NONE') %}
**Đang có lỗi:** {{ states('sensor.dryer_fault_text') }}. Khắc phục nguyên nhân rồi nhấn **Xóa lỗi** trước khi bật lại.
{% else %}
Hệ thống đang dừng. Nhấn **Bật tự động** để bắt đầu điều khiển theo thời tiết.
{% endif %}
{% else %}
## 🟠 TỰ ĐỘNG ĐANG TẮT
Đang điều khiển thủ công. Nhấn **Bật tự động** để chuyển về điều khiển theo thời tiết.
{% endif %}"""

def entity_card(title, ids):
    return {"type":"entities","title":title,"show_header_toggle":False,"entities":ids}

def row(key):
    return {"entity":f"sensor.dryer_{key}_text","name":NAMES[key]}
def button(cmd, label, icon):
    action={"action":"perform-action","perform_action":"button.press","target":{"entity_id":f"button.dryer_{cmd.lower()}"}}
    if cmd in ["OPEN","RESET"]: action["confirmation"]={"text":f"Gửi yêu cầu {label.lower()}? ESP32 vẫn kiểm tra điều kiện an toàn."}
    return {"type":"button","name":label,"icon":f"mdi:{icon}","tap_action":action}

dashboard={"title":"Giàn phơi nông sản","views":[{"title":"Giàn phơi","path":"overview","icon":"mdi:sprout","cards":[
    {"type":"markdown","content":AUTO_BANNER,"entity_id":["binary_sensor.dryer_online","sensor.dryer_mode","sensor.dryer_fault","sensor.dryer_fault_text"],"card_size":4},
    {"type":"markdown","content":"# Giàn phơi nông sản\nVị trí bạt chỉ được xác nhận bằng công tắc hành trình. **Đề xuất mở/đóng không có nghĩa là bạt đã tới vị trí đó.**"},
    entity_card("Tổng quan",[row(key) for key in ["online","mode","roof_position","cover_request","cover_reason","motion","fault"]]),
    {"type":"conditional","conditions":[{"entity":"binary_sensor.dryer_motor_output_enabled","state":"off"}],
     "card":{"type":"markdown","content":"**Đầu ra motor đang khóa.** Bạt chưa tự di chuyển. Trong mô phỏng, gạt công tắc hành trình đóng hoặc mở sang phải để xác nhận vị trí."}},
    {"type":"conditional","conditions":[{"entity":"binary_sensor.dryer_motor_output_enabled","state":"on"}],
     "card":{"type":"markdown","content":"**Đầu ra motor đã bật.** Khi thử Wokwi, motor chưa tự tác động công tắc hành trình. Trước 20 giây, gạt **LIMIT OPEN hoặc LIMIT CLOSE sang phải** để xác nhận hành trình đích; gạt về trái để nhả trước khi đi chiều ngược lại. Không bật đồng thời hai hành trình. Nếu quá thời gian, hệ thống dừng và tắt AUTO; kiểm tra rồi nhấn **Xóa lỗi**."}},
    {"type":"grid","columns":2,"square":False,"cards":[
        {"type":"gauge","entity":"sensor.dryer_temperature","name":"Nhiệt độ","min":-20,"max":80},
        {"type":"gauge","entity":"sensor.dryer_humidity","name":"Độ ẩm","min":0,"max":100,"severity":{"green":0,"yellow":70,"red":81}}]},
    entity_card("Môi trường",[row(key) for key in ["rain_adc","rain","light_adc","dark","dht_valid","safe_to_open"]]),
    {"type":"grid","title":"Chọn chế độ và điều khiển","columns":3,"square":False,"cards":[button(*args) for args in [
        ("OPEN","Mở bạt","arrow-expand-vertical"),("CLOSE","Đóng bạt","arrow-collapse-vertical"),
        ("STOP","Dừng bạt","stop"),("AUTO","Bật tự động","autorenew"),("MANUAL","Tắt tự động / dừng","hand-back-right"),("RESET","Xóa lỗi","restart-alert")]]},
    entity_card("Hành trình và bảo vệ",[row(key) for key in ["limit_closed","limit_open","limit_fault","estop","driver_fault","motor_output_enabled","motor_active","command_result"]]),
    {"type":"history-graph","title":"Nhiệt độ và độ ẩm · 24 giờ","hours_to_show":24,"entities":[{"entity":"sensor.dryer_temperature","name":"Nhiệt độ"},{"entity":"sensor.dryer_humidity","name":"Độ ẩm"}]},
    {"type":"history-graph","title":"Mưa và ánh sáng · 24 giờ","hours_to_show":24,"entities":[{"entity":"sensor.dryer_rain_adc","name":"Cảm biến mưa"},{"entity":"sensor.dryer_light_adc","name":"Cảm biến ánh sáng"}]},
    entity_card("Cảnh báo",[row(key) for key in ["humidity_warning","humidity_danger","rain","dht_valid","limit_fault"]]),
    {"type":"markdown","content":"**Nút dừng trên mạng không thay thế dừng khẩn vật lý.** Chuyển thủ công hoặc xóa lỗi đều đưa hệ thống về trạng thái dừng. Sau đó cần chọn lại chế độ. Khi thiết bị mất kết nối, trạng thái tự động hiển thị chưa xác nhận."}
]}]}

def generate(check=False):
    for relative,data in [("packages/dryer.yaml",package),("dashboards/dryer.yaml",dashboard)]:
        target=BASE/relative
        content="# Generated by tools/build-home-assistant.py; no credentials.\n"+yaml.safe_dump(data,allow_unicode=True,sort_keys=False)
        if check:
            if target.read_text(encoding="utf-8") != content: raise SystemExit(f"Out of date: {target}")
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(content,encoding="utf-8",newline="\n")

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--check",action="store_true")
    generate(parser.parse_args().check)
