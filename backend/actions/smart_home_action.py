"""
Module d'actions domotique (Tuya/smart home).
Expose handle(tool_name, args, tuya_agent) pour lister et contrôler les appareils.

Appareils supportés : ampoules (bulb), prises (plug), bandeaux LED (strip), variateurs (dimmer).
"""

from typing import Any


def _device_type(device: Any) -> str:
    """Retourne le type lisible d'un device Tuya."""
    if device.is_bulb:
        return "bulb"
    if device.is_plug:
        return "plug"
    if device.is_strip:
        return "strip"
    if device.is_dimmer:
        return "dimmer"
    return "unknown"


async def handle(tool_name: str, args: dict[str, Any], tuya_agent: Any) -> str:
    """
    Dispatche les actions domotique vers tuya_agent.

    Outils supportés :
    - list_smart_devices()
    - control_light(target, action, brightness?, color?)
      actions valides : turn_on | turn_off | set
    """
    try:
        if tool_name == "list_smart_devices":
            if not tuya_agent.devices:
                return "Aucun appareil Tuya détecté. Lance une découverte d'abord."

            lines: list[str] = []
            for ip, device in tuya_agent.devices.items():
                dev_type = _device_type(device)
                state = "[ON]" if device.is_on else "[OFF]"
                lines.append(f"{device.alias} (IP:{ip}, {dev_type}) {state}")
            return "\n".join(lines)

        elif tool_name == "control_light":
            target: str = args.get("target", args.get("ip", ""))
            action: str = args.get("action", "")
            brightness = args.get("brightness")
            color = args.get("color")

            if not target:
                return (
                    "Erreur : paramètre 'target' manquant. "
                    "Appelle list_smart_devices d'abord pour obtenir les alias."
                )

            if action == "turn_on":
                ok = await tuya_agent.turn_on(target)
                if not ok:
                    return f"Échec : impossible d'allumer '{target}'. Vérifie l'alias avec list_smart_devices."
                extra = ""
                if brightness is not None:
                    await tuya_agent.set_brightness(target, brightness)
                    extra += f" Luminosité : {brightness}%."
                if color is not None:
                    await tuya_agent.set_color(target, color)
                    extra += f" Couleur : {color}."
                return f"'{target}' allumé avec succès.{extra}"

            elif action == "turn_off":
                ok = await tuya_agent.turn_off(target)
                return (
                    f"'{target}' éteint." if ok
                    else f"Échec : impossible d'éteindre '{target}'."
                )

            elif action == "set":
                if brightness is not None:
                    await tuya_agent.set_brightness(target, brightness)
                if color is not None:
                    await tuya_agent.set_color(target, color)
                parts = []
                if brightness is not None:
                    parts.append(f"luminosité {brightness}%")
                if color is not None:
                    parts.append(f"couleur {color}")
                detail = ", ".join(parts) if parts else "aucun changement"
                return f"'{target}' mis à jour : {detail}."

            return f"Action '{action}' inconnue. Valeurs acceptées : turn_on, turn_off, set."

        return f"Outil domotique inconnu : {tool_name}"

    except Exception as e:
        return f"Erreur {tool_name} : {e}"
