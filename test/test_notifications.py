"""Notification transitions, without publishing real dryer states or commands."""
import copy
import json
from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest
from jinja2 import Environment

root=Path(__file__).resolve().parents[1]
config=runpy.run_path(str(root/'tools/build-home-assistant.py'))
env=Environment()
env.filters['to_json']=json.dumps
decision=env.from_string(config['decision']['value_template'])
automation=next(a for a in config['alerts'] if a['id']=='dryer_decision_changed')
condition=env.from_string(automation['conditions'][0]['value_template'])
message=env.from_string(config['DECISION_MESSAGE'])

def packet(**changes):
    result=dict(cover_request='OPEN',cover_reason='NORMAL',safety_status='SAFE',rain=False,dark=False,
                dht_valid=True,safe_to_open=True,fault='NONE',estop=False,driver_fault=False,
                limit_fault=False,humidity_pct=60,mode='AUTO',open_wait_remaining_s=0)
    result.update(changes)
    return result

class NotificationTests(unittest.TestCase):
    def test_only_decision_or_safety_changes_trigger(self):
        baseline=packet()
        signature=lambda data:decision.render(value_json=data)
        for key,value in [('humidity_pct',61),('open_wait_remaining_s',18)]:
            self.assertEqual(signature(baseline),signature(packet(**{key:value})))
        for key,value in [('cover_request','CLOSE'),('cover_reason','RAIN'),('safety_status','WARNING'),
                          ('rain',True),('dark',True),('dht_valid',False),('safe_to_open',False),
                          ('fault','MOTION_TIMEOUT'),('estop',True),('driver_fault',True),('limit_fault',True)]:
            self.assertNotEqual(signature(baseline),signature(packet(**{key:value})))
        self.assertLess(len(signature(packet(cover_reason='HUMIDITY_WARNING',fault='MOTION_TIMEOUT'))),255)

    def test_no_notifications_for_attribute_only_or_unavailable_updates(self):
        for previous,current,expected in [('same','same',False),('old','new',True),('old','unavailable',False),('old','unknown',False)]:
            trigger=SimpleNamespace(from_state=SimpleNamespace(state=previous),to_state=SimpleNamespace(state=current))
            self.assertEqual(condition.render(trigger=trigger).strip()=='True',expected)
        self.assertEqual(automation['triggers'][0]['to'],None)
        self.assertEqual(automation['mode'],'queued')
        self.assertNotIn('notification_id',automation['actions'][0]['data'])
        self.assertEqual([a['action'] for a in automation['actions']],['persistent_notification.create'])

    def test_warning_message_requires_user_action_not_automatic_closing(self):
        data=packet(cover_request='CLOSE',cover_reason='HUMIDITY_WARNING',safety_status='WARNING',humidity_pct=75,safe_to_open=False)
        rendered=message.render(trigger=SimpleNamespace(to_state=SimpleNamespace(attributes=data)))
        self.assertIn('Đóng bạt',rendered)
        self.assertIn('không tự đóng',rendered)
        self.assertIn('75%',rendered)
        danger=copy.copy(data);danger.update(cover_reason='HUMIDITY_DANGER',safety_status='DANGER',humidity_pct=85)
        rendered=message.render(trigger=SimpleNamespace(to_state=SimpleNamespace(attributes=danger)))
        self.assertIn('Nguy hiểm',rendered)
        self.assertIn('AUTO đang bật',rendered)

if __name__=='__main__':unittest.main()
