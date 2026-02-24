import json
import os


_raw_lights_map = os.getenv("LIGHTS_MAP", "{}")
LIGHTS_MAP: dict[str, str] = json.loads(_raw_lights_map)
