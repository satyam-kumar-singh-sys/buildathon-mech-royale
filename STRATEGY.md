# Mech Royale strategy — review draft

**Status:** Initial, unvalidated hypothesis, not a demonstrated winning strategy. The official kit, map and recorded-stream checker have been obtained; the kit contains no simulator or match results. The implementation is a starting point, not a submission recommendation. Current competition announcement says 96 practice matches; the attached protocol mentions 48, so treat the announcement/scorer as authoritative and verify current rules.

## Objective and opponent model

Maximize expected placement, not kills. Practice is unusual: house bots cooperate and progressively hunt the player, so a strategy optimized for normal free-for-all play may perform very differently in practice versus qualifying/finals. Survivability, regeneration, safe rotation, and avoiding being surrounded are likely more valuable than chasing damage. However, zero kills may leave the entire squad alive late; the correct balance is an empirical question, not an established fact.

## Current baseline

- **Movement:** stay inside the current circle with a 25 m margin, and gradually move toward a 35 m margin inside the next circle. Repel from up to four visible nearby enemy mechs. Boost when threatened or near the zone edge if energy exceeds 25, otherwise conserve energy until above 75.
- **Survival:** avoid initiating fights with NPCs and crates; combat prevents healing for five seconds and may attract attention. Pick nearby accessible cubes and a second weapon opportunistically if no enemy is within 100 m. Seek nearby drops when no enemy is within 130 m.
- **Fighting:** face the closest visible mech while retreating to reduce rear damage. Lead gun shots using target velocity and projectile speed, and fire only when roughly aligned. Fire lightning at short range. Charge/release a laser at range. Do not fire the mortar yet: it requires a separate ballistic aim solution. Never intentionally swap weapons.
- **Upgrades:** favor armor, mobility/energy, regeneration, sensors, then gun damage/rate. Unknown upgrade IDs get a neutral priority; exact IDs and effects must be checked against the kit/config.
- **Unsticking and map:** a spatial index of the static prisms selects a locally clear heading using cylinder clearance and elevation; low displacement triggers a two-second perpendicular escape attempt. This is local steering, not global pathfinding. The map also provides an approximate sampled line-of-fire check.
- **Vision:** scan when no enemy is visible. Remember that enemies in the protocol may include tracked positions behind cover; visibility/line of sight needs verification against the actual schema and engine.

All thresholds above are heuristic and mostly use documented default rules, not fitted values. Only a few values currently use live configuration; balance changes can invalidate assumptions. The actual kit confirms upgrade IDs such as `plating`, `servos`, `jets`, and `nanites`; the priorities now use them.

## Important gaps and risks for reviewers

1. **Incomplete map navigation and line-of-fire checks.** Local steering can still trap us in concave obstacles; it does not model terrain, routes around large buildings, or height changes ahead. Sampled shot checks can miss thin geometry and do not model terrain. A terrain-aware navigation graph and exact height-aware line of sight are top priorities. Handle bridges, roofs, holes, and terrain; don't treat all geometry as ground-level rectangles.
2. **No projectile dodging or threat memory.** Use projectile closest-approach and damage bearings, avoiding movement into crossfire. Sound bearings are noisy: use as probabilistic signals, not exact enemy locations.
3. **Retreat may underperform.** All house bots are one squad and may eventually overwhelm a passive bot. Compare against selective focus fire, early crate farming, and NPC kills. Measure placement, survival time, kills, damage taken, zone damage, and cubes.
4. **Laser and multiweapon aiming:** gun lead is not correct for hitscan laser; firing both with a shared aim is an approximation. Laser slows movement and charging is dangerous. Mortar is intentionally not used. Add weapon-specific targeting, timing, line of sight, and self-splash safety.
5. **Drop capture:** the simple controller may drift away or contest a drop. Detect holder/progress, stop inside the ring, and estimate contested risk. Avoid going to drops that draw the squad unless healing is worth it.
6. **Zone navigation:** next-zone urgency is distance-based, not time-to-close or route-length based; it may rotate unnecessarily early or too late behind obstacles. Predict shrink at arrival, calculate zone damage vs threat, and preserve energy for escape.
7. **Tick budget and conformance:** the official recorded check passed on the host (300/300, no late or bad answers; recorded run p99 5.3 ms, max 9.8 ms). The Docker sandbox remains untested because Docker is unavailable here. Raw stdin draining is designed to skip queued observations. The recorded stream cannot validate game performance, and timings on other machines will vary.
8. **Combat details:** verify actual upgrade IDs, reload behavior, weapon stat keys, hitbox sizes, aim slew, and enemy visibility fields. Select targets based on damage potential, HP, line of fire, and immediate threat instead of proximity alone.
9. **Finals transfer:** practice squad tactics can be actively wrong in a free-for-all. Build a separate strategy profile or adapt to observed behavior; finals may reward opportunistic third-party fights and harvesting.

## Experiment plan

1. Run the supplied checker in the exact container sandbox; the host check already passed. Confirm stdout, backlog handling, and latency headroom.
2. Acquire local simulation/replays or practice telemetry if provided. Establish baseline over many seeds and spawn slots; retain per-game results and uncertainty intervals. Practice seeds are fresh/private, so don't claim a paired comparison without controlled local seeds.
3. Run controlled ablations: passive vs selective aggression; rotations with vs without next-circle pressure; boost thresholds; crate/NPC farming; drops; weapon preferences. Change one family at a time. Use all four hourly submissions deliberately, not on untested changes.
4. Inspect failure cases (walls, zone deaths, squad encirclement, rooftop targets). Implement and benchmark geometry-aware navigation and aiming before adding model complexity.
5. Freeze pinned dependencies/image, pass the official sandbox check, then push the chosen commit on the current branch and submit its public URL through the competition page. Rebuild finalists with the same pinned inputs.

## Questions for reviewers

- Is passive evasion viable against the coordinated squad, or is early elimination of pursuers essential?
- How do house bots acquire/retain targets, and can buildings, quiet movement, or elevation break pursuit?
- Are damage/rear armor, weapon aim, upgrades, and laser charge mechanics modeled correctly here?
- Does the kit include an actual local simulator or only a recorded checker? What telemetry/replay tools exist?
- Which navigation and combat changes offer the best improvement per 50 ms tick on one CPU?

## Kit findings

The kit includes a static map and a 300-observation recorded check, not a local game engine or interactive simulator. The example bot is deliberately simple. The local checker cannot measure wins or react to our actions. Docker was not available in this environment; a sandboxed image build/check and practice submissions are still needed.
