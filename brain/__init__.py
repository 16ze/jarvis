"""
brain/ — cerveau biomimétique d'Ada.

Couches :
  - neurons      : NeuroneLIF (Leaky Integrate-and-Fire)
  - network      : ReseauAttention (couche sensorielle + thalamus)
  - lexicons     : 9 frozensets FR de sentiment
  - limbic       : CerveauEmotif (6 hormones + momentum)
  - mood         : derive_mood(...) -> ~50 états émotionnels
  - modulators   : mapping mood -> {temperature, thinking_budget}
  - mood_block   : générateur du bloc system_instruction injecté à Gemini
  - sensors_adapter : pont MediaPipe READ-ONLY via callback
  - brain_manager   : singleton façade (SEULE API qu'Ada consulte)

Le brain est observateur + modulateur. Jamais bloquant. Voice Kore figée.
"""

from brain.brain_manager import get_brain  # noqa: F401
