"""Small read-only spatial index for the arena's static prisms."""
import json
import math
import os


def in_ring(x, y, ring):
    inside = False
    n = len(ring)
    j = n - 2
    for i in range(0, n, 2):
        xi, yi, xj, yj = ring[i], ring[i+1], ring[j], ring[j+1]
        if (yi > y) != (yj > y) and x < (xj-xi)*(y-yi)/(yj-yi)+xi:
            inside = not inside
        j = i
    return inside


def edge_distance_sq(x, y, ring):
    best = float('inf')
    j = len(ring) - 2
    for i in range(0, len(ring), 2):
        ax, ay, bx, by = ring[j], ring[j+1], ring[i], ring[i+1]
        dx, dy = bx-ax, by-ay
        den = dx*dx+dy*dy
        u = max(0., min(1., ((x-ax)*dx+(y-ay)*dy)/den)) if den else 0.
        best = min(best, (x-ax-u*dx)**2+(y-ay-u*dy)**2)
        j = i
    return best


class World:
    def __init__(self, map_dir):
        with open(os.path.join(map_dir, 'v2', 'world.json')) as f:
            world = json.load(f)
        self.grid = {}
        self.bounds = world['bounds']
        for prism in world['prisms']:
            ring = prism.get('ring', [])
            if len(ring) < 6: continue
            xs, ys = ring[::2], ring[1::2]
            box = min(xs), min(ys), max(xs), max(ys)
            entry = (box, prism['base'], prism['top'], ring, prism.get('holes', []))
            # margin permits cylinder clearance checks across cell boundaries
            for x in range(math.floor((box[0]-8)/32), math.floor((box[2]+8)/32)+1):
                for y in range(math.floor((box[1]-8)/32), math.floor((box[3]+8)/32)+1):
                    self.grid.setdefault((x, y), []).append(entry)

    def blocked(self, x, y, low, high, radius=0):
        b = self.bounds
        if x-radius < b['minX'] or x+radius > b['maxX'] or y-radius < b['minY'] or y+radius > b['maxY']:
            return True
        for box, base, top, ring, holes in self.grid.get((math.floor(x/32), math.floor(y/32)), ()):
            if top <= low or base >= high or x < box[0]-radius or x > box[2]+radius or y < box[1]-radius or y > box[3]+radius:
                continue
            inside = in_ring(x, y, ring)
            if inside and any(in_ring(x, y, hole) and edge_distance_sq(x, y, hole) > radius*radius for hole in holes):
                inside = False
            if inside or (radius and edge_distance_sq(x, y, ring) < radius*radius):
                return True
        return False

    def clear_shot(self, a, b):
        d = math.dist(a, b)
        count = max(1, math.ceil(d / 3.0))
        for i in range(1, count):
            t = i/count
            x, y, z = (a[k]+(b[k]-a[k])*t for k in range(3))
            if self.blocked(x, y, z-0.1, z+0.1):
                return False
        return True

    def steer(self, pos, vector, radius, height):
        """Choose a short collision-free heading, preserving original preference."""
        x, y = vector
        if not x and not y: return vector
        angle = math.atan2(y, x)
        # Prefer small turns, but leave room for side-stepping rather than
        # persistently pressing against walls. Geometry is a local approximation.
        for offset in (0, .35, -.35, .7, -.7, 1.05, -1.05, 1.4, -1.4, 1.9, -1.9, 2.5, -2.5, math.pi):
            dx, dy = math.cos(angle+offset), math.sin(angle+offset)
            if all(not self.blocked(pos[0]+dx*d, pos[1]+dy*d, pos[2]+1.2, pos[2]+height, radius+0.5) for d in (4, 8, 13)):
                return [dx, dy]
        return vector
