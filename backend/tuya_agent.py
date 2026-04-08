import asyncio
import json
import os
from pathlib import Path

try:
    import tinytuya
except ImportError:
    tinytuya = None
    print("[TuyaAgent] WARNING: tinytuya not installed. Run: pip install tinytuya")

DEVICES_JSON = Path(__file__).parent / "devices.json"
TUYA_REGION = os.getenv("TUYA_REGION", "eu")

# Categories that tinytuya wizard tags as lights/bulbs
_BULB_CATEGORIES = {"dj", "dc", "dd", "fwd", "fwl", "tgq", "tgkg", "xdd", "bulb", "light"}

COLOR_MAP = {
    "red": (0, 100, 100),
    "orange": (30, 100, 100),
    "yellow": (60, 100, 100),
    "green": (120, 100, 100),
    "cyan": (180, 100, 100),
    "blue": (240, 100, 100),
    "purple": (300, 100, 100),
    "pink": (300, 50, 100),
    "white": (0, 0, 100),
    "warm": (30, 20, 100),
    "cool": (200, 10, 100),
    "daylight": (0, 0, 100),
}


class TuyaDevice:
    """
    Wrapper around a tinytuya device that exposes the same attribute interface
    as python-kasa SmartDevice objects (alias, model, is_on, is_bulb, is_plug,
    is_strip, is_dimmer, is_color, is_dimmable, brightness, hsv).
    This allows ada.py to iterate over TuyaAgent.devices without modification.
    """

    def __init__(self, name: str, device_id: str, key: str, ip: str,
                 device_type: str = "plug", version: str = "3.3"):
        self.alias = name
        self.id = device_id
        self.key = key
        self.ip = ip
        self.model = "Tuya"
        self.version = version
        self._device_type = device_type  # "bulb" | "plug"
        self.is_on: bool = False
        self._brightness: int | None = None  # 0-100
        self._hsv: tuple | None = None

        if tinytuya:
            if device_type == "bulb":
                self._tuya = tinytuya.BulbDevice(device_id, ip, key)
            else:
                self._tuya = tinytuya.OutletDevice(device_id, ip, key)
            try:
                self._tuya.set_version(float(version))
                self._tuya.set_socketTimeout(2)
                self._tuya.set_socketRetryLimit(1)
            except Exception:
                pass
        else:
            self._tuya = None

    # ── Kasa-compatible properties ──────────────────────────────────────────
    @property
    def is_bulb(self) -> bool:
        return self._device_type == "bulb"

    @property
    def is_plug(self) -> bool:
        return self._device_type == "plug"

    @property
    def is_strip(self) -> bool:
        return False

    @property
    def is_dimmer(self) -> bool:
        return self._device_type == "bulb"

    @property
    def is_color(self) -> bool:
        return self._device_type == "bulb"

    @property
    def is_dimmable(self) -> bool:
        return self._device_type == "bulb"

    @property
    def brightness(self) -> int | None:
        return self._brightness

    @property
    def hsv(self) -> tuple | None:
        return self._hsv

    # ── Synchronous operations (run via asyncio.to_thread) ──────────────────

    def _sync_status(self):
        if not self._tuya:
            return
        try:
            data = self._tuya.status()
            dps = data.get("dps", {})
            if self.is_bulb:
                self.is_on = bool(dps.get("20", False))
                # DPS 22: brightness 10-1000 → normalize to 0-100
                raw = dps.get("22", 0)
                self._brightness = max(0, min(100, int(raw / 10))) if raw else 0
                # DPS 24: colour_data_v2 — hex string HHHHSSSSSVVVV (each 4 hex chars)
                # e.g. "000003e803e8" → h=0, s=1000, v=1000
                colour_raw = dps.get("24", "")
                if colour_raw and isinstance(colour_raw, str) and len(colour_raw) == 12:
                    try:
                        h_raw = int(colour_raw[0:4], 16)   # 0-360
                        s_raw = int(colour_raw[4:8], 16)   # 0-1000
                        v_raw = int(colour_raw[8:12], 16)  # 0-1000
                        self._hsv = (h_raw, int(s_raw / 10), int(v_raw / 10))
                    except Exception:
                        pass
            else:
                self.is_on = bool(dps.get("1", False))
        except Exception as e:
            print(f"[TuyaAgent] Status error for '{self.alias}' ({self.ip}): {e}")

    def _sync_turn_on(self) -> bool:
        if not self._tuya:
            return False
        try:
            self._tuya.turn_on()
            self.is_on = True
            return True
        except Exception as e:
            print(f"[TuyaAgent] turn_on error for '{self.alias}': {e}")
            return False

    def _sync_turn_off(self) -> bool:
        if not self._tuya:
            return False
        try:
            self._tuya.turn_off()
            self.is_on = False
            return True
        except Exception as e:
            print(f"[TuyaAgent] turn_off error for '{self.alias}': {e}")
            return False

    def _sync_set_brightness(self, value: int) -> bool:
        """
        value: 0-100 → DPS 22: 10-1000 (LSC minimum is 10).
        Switches to 'white' mode first so brightness DPS takes effect.
        """
        if not self._tuya or not self.is_bulb:
            return False
        try:
            tuya_val = max(10, min(1000, int(value * 10)))
            self._tuya.set_value(21, "white")
            self._tuya.set_value(22, tuya_val)
            self._brightness = int(value)
            return True
        except Exception as e:
            print(f"[TuyaAgent] set_brightness error for '{self.alias}': {e}")
            return False

    def _sync_set_hsv(self, h: int, s: int, v: int) -> bool:
        """
        h: 0-360, s: 0-100, v: 0-100 (Ada/Kasa convention).
        LSC DPS 24 (colour_data_v2) uses a 12-char hex string: HHHHSSSSSVVVV
        where H is 0-360 and S/V are 0-1000.
        Switches work_mode to 'colour' (DPS 21) before setting.
        """
        if not self._tuya or not self.is_bulb:
            return False
        try:
            h_val = int(h)               # 0-360
            s_val = int(s * 10)          # 0-100 → 0-1000
            v_val = int(v * 10)          # 0-100 → 0-1000
            hex_colour = f"{h_val:04x}{s_val:04x}{v_val:04x}"
            self._tuya.set_value(21, "colour")
            self._tuya.set_value(24, hex_colour)
            self._hsv = (h, s, v)
            return True
        except Exception as e:
            print(f"[TuyaAgent] set_hsv error for '{self.alias}': {e}")
            return False


class TuyaAgent:
    """
    Drop-in replacement for KasaAgent using tinytuya for local Tuya device control.

    Devices are configured via devices.json (generated by `python -m tinytuya wizard`
    or created manually). Expected format:
        [{"name": "...", "id": "...", "key": "...", "ip": "...", "type": "bulb|plug"}]

    The public interface mirrors KasaAgent exactly:
        initialize(), discover_devices(), turn_on(target), turn_off(target),
        set_brightness(target, value), set_color(target, color_name),
        get_device_by_alias(alias), control_device(target, action, ...)
    """

    def __init__(self, known_devices=None):
        self.devices: dict[str, TuyaDevice] = {}  # {ip: TuyaDevice}
        self.known_devices_config: list = known_devices or []

    async def initialize(self):
        """Load devices from devices.json. Returns quietly if file is absent."""
        device_configs = self._load_device_configs()
        if not device_configs:
            print("[TuyaAgent] No devices configured (devices.json absent or empty).")
            return

        print(f"[TuyaAgent] Initializing {len(device_configs)} device(s)...")
        tasks = []
        for cfg in device_configs:
            ip = cfg.get("ip")
            name = cfg.get("name") or cfg.get("alias", "Unknown")
            dev_id = cfg.get("id")
            key = cfg.get("key")
            if not all([ip, dev_id, key]):
                print(f"[TuyaAgent] Skipping incomplete entry: {cfg}")
                continue

            device_type = self._detect_type(cfg)
            version = str(cfg.get("version", "3.3"))

            dev = TuyaDevice(name, dev_id, key, ip, device_type, version)
            self.devices[ip] = dev
            tasks.append(asyncio.to_thread(dev._sync_status))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for dev, result in zip(list(self.devices.values()), results):
            if isinstance(result, Exception):
                print(f"[TuyaAgent] Could not reach '{dev.alias}' ({dev.ip}): {result}")
            else:
                print(f"[TuyaAgent] Loaded '{dev.alias}' ({dev.ip}) {'ON' if dev.is_on else 'OFF'}")

    def _load_device_configs(self) -> list:
        if DEVICES_JSON.exists():
            try:
                with open(DEVICES_JSON) as f:
                    return json.load(f)
            except Exception as e:
                print(f"[TuyaAgent] Error reading devices.json: {e}")
        if self.known_devices_config:
            return self.known_devices_config
        return []

    @staticmethod
    def _detect_type(cfg: dict) -> str:
        explicit = cfg.get("type", "").lower()
        if explicit in ("bulb", "light"):
            return "bulb"
        if explicit in ("plug", "outlet", "switch"):
            return "plug"
        category = cfg.get("category", "").lower()
        if category in _BULB_CATEGORIES:
            return "bulb"
        return "plug"

    async def discover_devices(self) -> list:
        """Refresh device states and return list of dicts (Kasa-compatible format)."""
        if not self.devices:
            await self.initialize()
        else:
            tasks = [asyncio.to_thread(dev._sync_status) for dev in self.devices.values()]
            await asyncio.gather(*tasks, return_exceptions=True)

        device_list = []
        for ip, dev in self.devices.items():
            device_list.append({
                "ip": ip,
                "alias": dev.alias,
                "model": dev.model,
                "type": dev._device_type,
                "is_on": dev.is_on,
                "brightness": dev._brightness if dev.is_bulb else None,
                "hsv": dev._hsv if dev.is_bulb else None,
                "has_color": dev.is_bulb,
                "has_brightness": dev.is_bulb,
            })

        print(f"[TuyaAgent] Total devices: {len(device_list)}")
        return device_list

    def get_device_by_alias(self, alias: str) -> TuyaDevice | None:
        """Retourne le premier appareil correspondant (compatibilité)."""
        matches = self.get_devices_by_alias(alias)
        return matches[0] if matches else None

    def get_devices_by_alias(self, alias: str) -> list[TuyaDevice]:
        """
        Retourne tous les appareils dont l'alias correspond exactement (insensible à la casse).
        Les appareils avec le même alias forment un groupe naturel (ex: 4 × "Couloir").
        """
        alias_lower = alias.lower()
        return [dev for dev in self.devices.values() if dev.alias.lower() == alias_lower]

    def _resolve_group(self, target: str) -> list[TuyaDevice]:
        """
        Résout un target (IP ou alias) en liste d'appareils.
        1. IP exacte
        2. Alias exact (insensible à la casse)
        3. Alias contient le target (ex: "salon" → "Salon", "Lampe salon")
        4. Target contient l'alias (ex: "lumières du salon" → "Salon")
        """
        if target in self.devices:
            return [self.devices[target]]

        # Exact alias match
        matches = self.get_devices_by_alias(target)
        if matches:
            print(f"[TuyaAgent] '{target}' → {len(matches)} device(s) [exact]: {[d.alias for d in matches]}")
            return matches

        # Partial match: alias contains target OR target contains alias
        target_lower = target.lower()
        partial = [
            d for d in self.devices.values()
            if target_lower in d.alias.lower() or d.alias.lower() in target_lower
        ]
        if partial:
            print(f"[TuyaAgent] '{target}' → {len(partial)} device(s) [partial]: {[d.alias for d in partial]}")
            return partial

        print(f"[TuyaAgent] Device/group not found: '{target}'")
        return []

    async def turn_on(self, target: str) -> bool:
        devs = self._resolve_group(target)
        if not devs:
            return False
        results = await asyncio.gather(*[asyncio.to_thread(d._sync_turn_on) for d in devs])
        ok = any(results)
        print(f"[TuyaAgent] turn_on '{target}' ({len(devs)} device(s)): {'OK' if ok else 'FAILED'}")
        return ok

    async def turn_off(self, target: str) -> bool:
        devs = self._resolve_group(target)
        if not devs:
            return False
        results = await asyncio.gather(*[asyncio.to_thread(d._sync_turn_off) for d in devs])
        ok = any(results)
        print(f"[TuyaAgent] turn_off '{target}' ({len(devs)} device(s)): {'OK' if ok else 'FAILED'}")
        return ok

    async def set_brightness(self, target: str, value) -> bool:
        devs = self._resolve_group(target)
        if not devs:
            return False
        results = await asyncio.gather(*[asyncio.to_thread(d._sync_set_brightness, int(value)) for d in devs])
        return any(results)

    async def set_color(self, target: str, color_input) -> bool:
        devs = self._resolve_group(target)
        if not devs:
            return False

        hsv = None
        if isinstance(color_input, str):
            hsv = COLOR_MAP.get(color_input.lower().strip())
        elif isinstance(color_input, (tuple, list)) and len(color_input) == 3:
            hsv = tuple(color_input)

        if not hsv:
            print(f"[TuyaAgent] Unknown color: '{color_input}'")
            return False

        h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])
        results = await asyncio.gather(*[asyncio.to_thread(d._sync_set_hsv, h, s, v) for d in devs if d.is_bulb])
        return any(results)

    async def refresh_devices(self) -> str:
        """
        Refetch device names from Tuya cloud API and rebuild devices.json in-place.
        Keeps local IPs and keys from existing devices.json — only updates names.
        """
        import os, shutil
        api_key    = os.getenv("TUYA_API_KEY", "")
        api_secret = os.getenv("TUYA_API_SECRET", "")
        api_region = os.getenv("TUYA_API_REGION", "eu")

        if not api_key or not api_secret:
            return "Erreur : TUYA_API_KEY / TUYA_API_SECRET manquants dans .env"

        if not tinytuya:
            return "Erreur : tinytuya non installé"

        try:
            cloud = tinytuya.Cloud(
                apiRegion=api_region,
                apiKey=api_key,
                apiSecret=api_secret,
            )
            cloud_devices = await asyncio.to_thread(cloud.getdevices)
        except Exception as e:
            return f"Erreur connexion Tuya cloud : {e}"

        if not cloud_devices or not isinstance(cloud_devices, list):
            return f"Aucun appareil retourné par l'API Tuya (réponse : {cloud_devices})"

        # Load existing devices.json to keep local IPs / keys / version
        local_entries = []
        if DEVICES_JSON.exists():
            try:
                local_entries = json.load(open(DEVICES_JSON))
            except Exception:
                pass

        # Back up
        if DEVICES_JSON.exists():
            shutil.copy(DEVICES_JSON, str(DEVICES_JSON) + ".bak")

        # Map device id → local entry
        local_map = {d["id"]: d for d in local_entries if d.get("id")}

        # Map device id → cloud name
        cloud_map = {dev.get("id", ""): dev for dev in cloud_devices if dev.get("id")}

        changes = []
        # Update names in existing entries
        for dev_id, cloud_dev in cloud_map.items():
            new_name = cloud_dev.get("name", "")
            if dev_id in local_map:
                old_name = local_map[dev_id].get("name", "")
                if old_name != new_name:
                    changes.append(f"{old_name} → {new_name} ({local_map[dev_id].get('ip', '?')})")
                local_map[dev_id]["name"] = new_name
            else:
                # New device not in local — add with cloud IP (might be WAN, not ideal)
                local_map[dev_id] = {
                    "name":     new_name,
                    "id":       dev_id,
                    "key":      cloud_dev.get("local_key", cloud_dev.get("key", "")),
                    "ip":       cloud_dev.get("ip", ""),
                    "category": cloud_dev.get("category", ""),
                    "version":  "3.3",
                }
                changes.append(f"[NOUVEAU] {new_name}")

        # Save tuya-raw.json
        raw_path = DEVICES_JSON.parent / "tuya-raw.json"
        try:
            with open(raw_path, "w") as f:
                json.dump({"result": cloud_devices, "success": True}, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # Save updated devices.json
        updated_list = list(local_map.values())
        with open(DEVICES_JSON, "w") as f:
            json.dump(updated_list, f, indent=2, ensure_ascii=False)

        # Reload in-memory state
        self.devices.clear()
        await self.initialize()

        summary = f"{len(cloud_devices)} appareils synchronisés depuis Tuya cloud."
        if changes:
            summary += "\nChangements :\n" + "\n".join(f"  • {c}" for c in changes)
        else:
            summary += "\nAucun changement de nom détecté."
        return summary

    async def control_device(self, target: str, action: str,
                              brightness=None, color_temp=None) -> bool:
        """Compatibility shim for _execute_text_tool calls in ada.py."""
        if action in ("on", "turn_on"):
            return await self.turn_on(target)
        elif action in ("off", "turn_off"):
            return await self.turn_off(target)
        elif action == "brightness" and brightness is not None:
            return await self.set_brightness(target, brightness)
        return False


# ── Standalone test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def main():
        agent = TuyaAgent()
        devices = await agent.discover_devices()
        print("Devices:", devices)

    asyncio.run(main())
