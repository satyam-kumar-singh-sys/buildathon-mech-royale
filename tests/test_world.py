import json
import os
import tempfile
import unittest
from world import World


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, 'v2'))
        world = {'bounds': {'minX': -100, 'minY': -100, 'maxX': 100, 'maxY': 100},
                 'prisms': [
                     {'base': 0, 'top': 20, 'ring': [10, -10, 20, -10, 20, 10, 10, 10], 'holes': []},
                     {'base': 15, 'top': 17, 'ring': [-20, -10, -10, -10, -10, 10, -20, 10], 'holes': []},
                     {'base': 0, 'top': 20, 'ring': [30, -10, 50, -10, 50, 10, 30, 10],
                      'holes': [[35, -5, 45, -5, 45, 5, 35, 5]]}]}
        with open(os.path.join(self.tmp.name, 'v2', 'world.json'), 'w') as f: json.dump(world, f)
        self.world = World(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def test_footprint_clearance_and_hole(self):
        self.assertTrue(self.world.blocked(9, 0, 1, 9, 2))
        self.assertFalse(self.world.blocked(40, 0, 1, 9, 2))
        self.assertTrue(self.world.blocked(35.5, 0, 1, 9, 2))
    def test_bridge_and_shot(self):
        self.assertFalse(self.world.blocked(-15, 0, 1, 9, 2))
        self.assertTrue(self.world.blocked(-15, 0, 16, 16.2))
        self.assertFalse(self.world.clear_shot([0, 0, 7], [25, 0, 7]))
        self.assertTrue(self.world.clear_shot([0, 0, 25], [25, 0, 25]))
    def test_steer_around_wall(self):
        move = self.world.steer([0, 0, 0], [1, 0], 2.5, 9)
        self.assertNotAlmostEqual(move[1], 0)

if __name__ == '__main__': unittest.main()
