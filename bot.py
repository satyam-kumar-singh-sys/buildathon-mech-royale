#!/usr/bin/env python3
"""Mech Royale survival-oriented starter. Standard library only."""
import json
import math
import os
import select
import sys
import traceback

from world import World


def norm(x, y):
    d = math.hypot(x, y)
    return (x / d, y / d) if d > 1e-9 else (0.0, 0.0)


def angle_diff(a, b):
    return (a - b + math.pi) % (2 * math.pi) - math.pi


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class Pilot:
    def __init__(self, hello):
        self.config = hello.get('config', {})
        self.world = None
        try:
            self.world = World(hello.get('map', {}).get('dir', '/arena'))
        except (OSError, ValueError, KeyError):
            pass  # The official map may be absent in standalone tests.
        self.seed = hello.get('seed', 0)
        self.last_pos = None
        self.stuck = 0
        self.escape_until = 0
        self.escape_side = 1

    def act(self, o):
        me = o['self']
        p = me['pos']
        t = o.get('t', 0)
        weapons = me.get('weapons', [])
        action = {'tick': o['tick'], 'move': [0, 0], 'fire': [False, False]}
        energy = me.get('energy', 0)
        zone = o.get('zone') or {}
        center = zone.get('center', p)
        nxt = zone.get('next_center', center)
        radius = zone.get('radius', 560)
        next_radius = zone.get('next_radius', radius)
        # A forward-looking safe point, but do not rush the center: the edge
        # is typically less exposed and leaves more room to escape.
        dnext = distance(p, nxt)
        urgency = max(0.0, dnext - max(0, next_radius - 35))
        dc = distance(p, center)
        outside = dc > radius - 25
        vx = vy = 0.0
        if outside:
            x, y = norm(center[0] - p[0], center[1] - p[1])
            vx += 4*x; vy += 4*y
        if urgency > 0:
            x, y = norm(nxt[0] - p[0], nxt[1] - p[1])
            weight = min(2.5, 0.3 + urgency / 70)
            vx += weight*x; vy += weight*y

        enemies = [e for e in o.get('mechs', []) if e.get('kind') == 'mech' and e.get('id') != me.get('id')]
        enemies.sort(key=lambda e: distance(p, e['pos']))
        nearest = enemies[0] if enemies else None
        threat_dist = distance(p, nearest['pos']) if nearest else 9999
        # Escape rather than seek an outnumbered fight; don't flee so hard that
        # the zone becomes lethal. Torso remains independent of movement.
        for e in enemies[:4]:
            d = distance(p, e['pos'])
            if d < 185:
                x, y = norm(p[0]-e['pos'][0], p[1]-e['pos'][1])
                weight = 2.8 * (185-d)/185
                vx += x*weight; vy += y*weight
        # Opportunistic nearby loot only when no immediate threat.
        held = {w.get('kind') for w in weapons if w}
        candidates = []
        for cube in o.get('cubes', []):
            if abs(cube['pos'][2]-p[2]) < 4 and distance(p, cube['pos']) < 40:
                candidates.append((distance(p, cube['pos']) - 10, cube))
        for item in o.get('pickups', []):
            if len(weapons) >= 2 and all(weapons) or item.get('kind') in held:
                continue
            if item.get('kind') not in ('laser', 'lightning', 'mortar'):
                continue
            d = distance(p, item['pos'])
            if abs(item['pos'][2]-p[2]) < 4 and d < 35:
                candidates.append((d - (12 if item['kind'] == 'laser' else 5), item))
                if d < self.config.get('loot', {}).get('pickup_radius', 4) - 0.3:
                    action['take'] = item['id']
        if candidates and threat_dist > 100 and not outside:
            obj = min(candidates, key=lambda item: item[0])[1]
            x, y = norm(obj['pos'][0]-p[0], obj['pos'][1]-p[1])
            vx += 1.4*x; vy += 1.4*y

        # Uncontested drops offer healing; avoid deliberately running into combat.
        if threat_dist > 130 and not outside:
            for drop in o.get('drops', []):
                d = distance(p, drop['pos'])
                if d < 90 and drop.get('lands_in', 0) < d / 12 + 4 and abs(drop['pos'][2]-p[2]) < 8:
                    if d > 4:
                        x, y = norm(drop['pos'][0]-p[0], drop['pos'][1]-p[1])
                        vx += 1.2*x; vy += 1.2*y
                    break

        # Wall recovery: turn away from a blocked path for a short interval.
        moving = math.hypot(vx, vy) > 0.3
        if self.last_pos is not None and moving and me.get('grounded', True):
            if distance(p, self.last_pos) < 0.25:
                self.stuck += 1
            else:
                self.stuck = max(0, self.stuck - 1)
            if self.stuck >= 12:
                self.escape_until = t + 2.0
                self.escape_side *= -1
                self.stuck = 0
        self.last_pos = p[:]
        if t < self.escape_until:
            vx, vy = -vy*self.escape_side, vx*self.escape_side
        if moving:
            action['move'] = list(norm(vx, vy))
            if self.world and me.get('grounded', True):
                stats = me.get('stats', {})
                action['move'] = self.world.steer(p, action['move'], stats.get('radius', 2.5), stats.get('height', 9))
            action['boost'] = energy > (25 if threat_dist < 150 or outside else 75)

        offer = o.get('offer')
        if offer and offer.get('choices'):
            weights = {'armor': 100, 'plating': 95, 'servos': 90, 'jets': 88,
                       'nanites': 85, 'reactor': 80, 'capacitor': 70,
                       'sensors': 65, 'laser_damage': 60, 'laser_charge': 58,
                       'gun_damage': 55, 'gun_rate': 50}
            choices = offer['choices']
            action['pick'] = max(range(len(choices)), key=lambda i: weights.get(choices[i].get('id'), 30))

        # Shoot visible enemies while retreating. Crates and NPCs are intentionally
        # avoided: damage interrupts regeneration and attracts the house squad.
        if nearest:
            ep = nearest['pos']; vel = nearest.get('vel', [0, 0, 0])
            muzzle = me.get('stats', {}).get('muzzle_height', 7)
            target_height = 4.5 * (1 + 0.05 * nearest.get('cubes', 0))
            gun = next((w for w in weapons if w and w.get('kind') == 'gun'), None)
            speed = (gun or {}).get('stats', {}).get('speed', 252)
            # A charged laser is hitscan: align on current target position.
            charging = any(w and w.get('kind') == 'laser' and w.get('charge', 0) > 0 for w in weapons)
            lead = 0 if charging else min(1.2, threat_dist / max(speed, 1))
            dx = ep[0] + vel[0]*lead - p[0]
            dy = ep[1] + vel[1]*lead - p[1]
            dz = ep[2] + target_height + vel[2]*lead - (p[2]+muzzle)
            yaw = math.atan2(dy, dx)
            pitch = math.atan2(dz, max(0.01, math.hypot(dx, dy)))
            action['aim'] = [yaw, pitch]
            current = me.get('aim', [yaw, pitch])
            tolerance = max(0.012, min(0.12, 2.5 / max(threat_dist, 1)))
            aligned = abs(angle_diff(yaw, current[0])) < tolerance and abs(pitch-current[1]) < tolerance
            clear = not self.world or self.world.clear_shot([p[0], p[1], p[2]+muzzle], [ep[0]+vel[0]*lead, ep[1]+vel[1]*lead, ep[2]+target_height+vel[2]*lead])
            for i, weapon in enumerate(weapons[:2]):
                if not weapon: continue
                kind = weapon.get('kind')
                stats = weapon.get('stats', {})
                if kind == 'gun':
                    action['fire'][i] = aligned and clear and not charging and threat_dist < stats.get('range', 230)*0.95
                elif kind == 'lightning':
                    action['fire'][i] = aligned and clear and threat_dist < stats.get('range', 45)*0.9 and energy > 12
                elif kind == 'laser':
                    charge = weapon.get('charge', 0)
                    action['fire'][i] = threat_dist < stats.get('range', 280)*0.95 and clear and charge < stats.get('charge', 0.75) and (aligned or charge > 0)
                # Mortar needs ballistic aim, so don't fire it using gun aim.
        else:
            # Slow scan to discover threats and loot; look toward movement when traveling.
            yaw = math.atan2(vy, vx) if moving else (t * 0.5 + self.seed % 7)
            action['aim'] = [yaw, 0]
        return action


def send(obj):
    sys.stdout.write(json.dumps(obj, separators=(',', ':'), allow_nan=False) + '\n')
    sys.stdout.flush()


def main():
    # Read raw bytes to drain all already-queued observations without the hidden
    # buffering of TextIOWrapper. Keep hello/end and the newest observation.
    fd = sys.stdin.fileno()
    pending = b''
    pilot = None
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        pending += chunk
        while select.select([fd], [], [], 0)[0]:
            chunk = os.read(fd, 65536)
            if not chunk: break
            pending += chunk
        lines = pending.split(b'\n')
        pending = lines.pop()
        newest = None
        for line in lines:
            if not line: continue
            msg = json.loads(line)
            kind = msg.get('type')
            if kind == 'hello':
                pilot = Pilot(msg)
                send({'type': 'ready', 'name': 'Oval Sentinel'})
            elif kind == 'obs':
                newest = msg
            elif kind == 'end':
                return
        if newest is not None and pilot is not None:
            try:
                send(pilot.act(newest))
            except Exception:
                traceback.print_exc(file=sys.stderr)
                send({'tick': newest['tick']})


if __name__ == '__main__':
    main()
