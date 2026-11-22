# Oval Sentinel — Mech Royale

Initial survival-oriented Python bot for the `mechfight/1` protocol. This is an **unproven competition baseline**: it passes the kit's recorded checker on the host, but has not been checked in Docker or tested against scored matches. See [STRATEGY.md](STRATEGY.md) for the strategy, limitations, and review questions; [protocol.md](protocol.md) is the supplied protocol.

## Run locally

```sh
python3 -m unittest discover -s tests -v
python3 -u bot.py
```

The second command expects JSON-lines protocol input on stdin; stdout is reserved for protocol responses. The bot uses no Python dependencies and writes no files at runtime. It reads the map from `hello.map.dir` when available and falls back to map-free behavior otherwise.

## Official conformance check (requires the complete kit and Docker)

Place the official kit outside this repository or in an ignored local directory, then use its actual checker and map paths. In this workspace the extracted kit is at `kit/mechfight-kit` (ignored by Git). For example:

```sh
KIT="$PWD/kit/mechfight-kit"
python3 "$KIT/check/check.py" --map-dir "$KIT/arena" -- python3 -u bot.py
docker build -t oval-sentinel .
python3 "$KIT/check/check.py" --map-dir /arena -- docker run --rm -i --network none --cpus 1 --memory 512m --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 -v "$KIT/arena:/arena:ro" oval-sentinel
```

Adjust the map path to match the kit layout. The documented check is not a game simulation; passing it does not demonstrate match performance. After testing, push the current branch and submit the public repository/commit through the competition website.
