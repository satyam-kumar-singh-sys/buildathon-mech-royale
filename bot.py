#!/usr/bin/env python3
"""Mech Royale survival-oriented starter. Standard library only."""
import json
import math
import os
import select
import sys
import traceback
import time
import random

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
        self.rng = random.Random(self.seed)
        self.strafe_side = 1
        self.strafe_until = 0

    def act(self, o):
        started = time.perf_counter()
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
        # Vary escape direction under a nearby threat without sacrificing the
        # inward component when already outside the zone.
        if nearest and threat_dist < 160 and not outside:
            if t >= self.strafe_until:
                self.strafe_side = self.rng.choice((-1, 1))
                self.strafe_until = t + self.rng.uniform(0.6, 1.2)
            ax, ay = norm(p[0] - nearest['pos'][0], p[1] - nearest['pos'][1])
            vx -= ay * self.strafe_side * 1.2
            vy += ax * self.strafe_side * 1.2

        # Move out of the way of a projectile whose closest approach is imminent.
        # The short horizon avoids overreacting to distant shots or mortar arcs.
        for proj in o.get('projectiles', [])[:32]:
            q, vel = proj['pos'], proj['vel']
            dx, dy = q[0]-p[0], q[1]-p[1]
            relx = vel[0] - me.get('vel', [0, 0, 0])[0]
            rely = vel[1] - me.get('vel', [0, 0, 0])[1]
            speed2 = relx*relx + rely*rely
            if speed2 < 1: continue
            impact = -(dx*relx + dy*rely) / speed2
            z = q[2] + vel[2] * impact
            if 0 < impact < 0.8 and p[2] - 4 < z < p[2] + me.get('stats', {}).get('height', 9) + 4 and math.hypot(dx + impact*relx, dy + impact*rely) < 8:
                side = 1 if dx*rely - dy*relx >= 0 else -1
                sx, sy = norm(-rely*side, relx*side)
                vx += 2*sx; vy += 2*sy

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

        # Early, healthy, uncontested crate farming supplies a first upgrade;
        # never wake a nearby NPC or divert far from a safe circle.
        crate_target = None
        npcs = [e for e in o.get('mechs', []) if e.get('kind') == 'npc']
        if (not nearest and not outside and urgency < 5 and t < 120
                and me.get('cubes', 0) < 3 and me.get('hp', 1400) >= 0.8 * me.get('max_hp', 1400)
                and all(distance(p, n['pos']) > 75 for n in npcs)):
            crates = [c for c in o.get('crates', []) if distance(p, c['pos']) < 55
                      and abs(c['pos'][2] - p[2]) < 3]
            if crates:
                crate_target = min(crates, key=lambda c: distance(p, c['pos']))
                if distance(p, crate_target['pos']) > 12 and not candidates:
                    x, y = norm(crate_target['pos'][0]-p[0], crate_target['pos'][1]-p[1])
                    vx += x; vy += y

        # Uncontested drops offer healing; avoid deliberately running into combat.
        capturing = False
        if threat_dist > 130 and not outside:
            for drop in o.get('drops', []):
                d = distance(p, drop['pos'])
                if d < 90 and drop.get('lands_in', 0) < d / 12 + 4 and abs(drop['pos'][2]-p[2]) < 8:
                    if d <= min(4, drop.get('radius', 8) * 0.6) and drop.get('lands_in', 0) <= 0:
                        capturing = True
                    elif d > 4:
                        x, y = norm(drop['pos'][0]-p[0], drop['pos'][1]-p[1])
                        vx += 1.2*x; vy += 1.2*y
                    break

        # Zone safety overrides threat, loot, and dodge when in damaging zone.
        if dc > radius:
            vx, vy = norm(center[0]-p[0], center[1]-p[1])
            vx *= 5; vy *= 5
            capturing = False
        elif capturing and not outside and urgency < 5:
            vx = vy = 0
            crate_target = None

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
        if t < self.escape_until and moving and dc <= radius:
            vx, vy = -vy*self.escape_side, vx*self.escape_side
        if moving:
            action['move'] = list(norm(vx, vy))
            if self.world and me.get('grounded', True) and time.perf_counter() - started < 0.012:
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

        # Shoot visible enemies while retreating; never intentionally attack NPCs.
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
            clear = not self.world or (time.perf_counter() - started < 0.012 and self.world.clear_shot([p[0], p[1], p[2]+muzzle], [ep[0]+vel[0]*lead, ep[1]+vel[1]*lead, ep[2]+target_height+vel[2]*lead]))
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
        elif crate_target:
            target = crate_target['pos']
            muzzle = me.get('stats', {}).get('muzzle_height', 7)
            dx, dy = target[0]-p[0], target[1]-p[1]
            yaw = math.atan2(dy, dx)
            pitch = math.atan2(target[2]+1.2-p[2]-muzzle, max(0.01, math.hypot(dx, dy)))
            action['aim'] = [yaw, pitch]
            current = me.get('aim', [yaw, pitch])
            tolerance = max(0.015, min(0.1, 1.0 / max(1, math.hypot(dx, dy))))
            aligned = abs(angle_diff(yaw, current[0])) < tolerance and abs(pitch-current[1]) < tolerance
            clear = not self.world or (time.perf_counter() - started < 0.012 and self.world.clear_shot([p[0], p[1], p[2]+muzzle], [target[0], target[1], target[2]+1.2]))
            for i, weapon in enumerate(weapons[:2]):
                if weapon and weapon.get('kind') == 'gun':
                    action['fire'][i] = aligned and clear
        else:
            # Slow scan to discover threats and loot; look toward movement when traveling.
            yaw = math.atan2(vy, vx) if moving else (t * 0.5 + self.seed % 7)
            action['aim'] = [yaw, 0]
        return action


def fallback(obs):
    # A valid non-firing response that keeps heading toward the safe circle.
    try:
        p = obs['self']['pos']
        zone = obs.get('zone') or {}
        goal = zone.get('center', p) if not obs['self'].get('in_zone', True) else zone.get('next_center', zone.get('center', p))
        return {'tick': obs['tick'], 'move': list(norm(goal[0]-p[0], goal[1]-p[1])), 'fire': [False, False]}
    except Exception:
        return {'tick': obs['tick'], 'fire': [False, False]}


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
                send(fallback(newest))


if __name__ == '__main__':
    main()
