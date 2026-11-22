import json
import subprocess
import sys
import unittest
from bot import Pilot


def observation(**extra):
    obj = {'type': 'obs', 'tick': 2, 't': 0, 'self': {'id': 1, 'pos': [0, 0, 0], 'aim': [0, 0], 'energy': 100, 'weapons': [{'kind': 'gun', 'stats': {'range': 230, 'speed': 252}}, None]}, 'zone': {'center': [0, 0], 'radius': 560, 'next_center': [0, 0], 'next_radius': 380}}
    obj.update(extra)
    return obj


class TestPilot(unittest.TestCase):
    def setUp(self): self.bot = Pilot({'config': {}, 'seed': 1})
    def test_enemy_aim_and_retreat(self):
        a = self.bot.act(observation(mechs=[{'id': 2, 'kind': 'mech', 'pos': [50, 0, 0], 'vel': [0, 0, 0]}]))
        self.assertLess(a['move'][0], 0)
        self.assertTrue(a['fire'][0])
    def test_zone_and_offer(self):
        a = self.bot.act(observation(zone={'center': [100, 0], 'radius': 50, 'next_center': [100, 0], 'next_radius': 20}, offer={'choices': [{'id': 'sensors'}, {'id': 'armor'}]}))
        self.assertGreater(a['move'][0], 0)
        self.assertEqual(a['pick'], 1)
    def test_pickup(self):
        a = self.bot.act(observation(pickups=[{'id': 8000, 'kind': 'laser', 'pos': [2, 0, 0]}]))
        self.assertEqual(a['take'], 8000)
    def test_stream_hello_obs_end(self):
        p = subprocess.Popen([sys.executable, '-u', 'bot.py'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        p.stdin.write(json.dumps({'type': 'hello', 'config': {}})+'\n'); p.stdin.flush()
        self.assertEqual(json.loads(p.stdout.readline())['type'], 'ready')
        p.stdin.write(json.dumps(observation())+'\n'); p.stdin.flush()
        self.assertEqual(json.loads(p.stdout.readline())['tick'], 2)
        p.stdin.write('{"type":"end"}\n'); p.stdin.close()
        self.assertEqual(p.wait(timeout=2), 0)
        p.stdout.close()

if __name__ == '__main__': unittest.main()
