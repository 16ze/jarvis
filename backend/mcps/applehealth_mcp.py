import os
import json
from datetime import datetime, timedelta

APPLE_HEALTH_EXPORT_PATH = os.getenv("APPLE_HEALTH_EXPORT_PATH", "")

EXPORT_INSTRUCTION = (
    "Export Apple Health introuvable. Pour exporter:\n"
    "1. Ouvrir l'app Santé sur iPhone\n"
    "2. Appuyer sur votre profil (en haut à droite)\n"
    "3. 'Exporter toutes les données de santé'\n"
    "4. Décompresser le fichier ZIP et définir APPLE_HEALTH_EXPORT_PATH "
    "vers le dossier apple_health_export/\n"
    "Note: certaines apps tierces (Health Auto Export) peuvent exporter en JSON."
)


def _parse_date(date_str: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str[:25], fmt[:len(date_str[:25])])
        except ValueError:
            continue
    return datetime.min


class AppleHealthMCP:
    def __init__(self):
        self._xml_root = None
        self._json_data = None
        self._format = None

    def _load_export(self) -> bool:
        if self._format:
            return True
        if not APPLE_HEALTH_EXPORT_PATH:
            return False
        export_path = APPLE_HEALTH_EXPORT_PATH.rstrip("/")

        # Tenter JSON d'abord (Health Auto Export)
        json_path = os.path.join(export_path, "HealthAutoExport.json")
        if not os.path.exists(json_path):
            json_path = os.path.join(export_path, "export.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    self._json_data = json.load(f)
                self._format = "json"
                return True
            except Exception:
                pass

        # Tenter XML (export natif Apple)
        xml_path = os.path.join(export_path, "export.xml")
        if os.path.exists(xml_path):
            try:
                import xml.etree.ElementTree as ET
                tree = ET.parse(xml_path)
                self._xml_root = tree.getroot()
                self._format = "xml"
                return True
            except Exception:
                pass

        return False

    def _get_xml_records(self, record_type: str, days: int):
        cutoff = datetime.now() - timedelta(days=days)
        records = []
        for record in self._xml_root.iter("Record"):
            if record.attrib.get("type") == record_type:
                end_date_str = record.attrib.get("endDate", "")
                if end_date_str:
                    try:
                        end_date = datetime.strptime(end_date_str[:19], "%Y-%m-%d %H:%M:%S")
                        if end_date >= cutoff:
                            records.append(record.attrib)
                    except ValueError:
                        pass
        return records

    def get_steps(self, days: int = 7) -> str:
        if not self._load_export():
            return EXPORT_INSTRUCTION if not APPLE_HEALTH_EXPORT_PATH else "Erreur AppleHealth: export introuvable dans le chemin spécifié."
        try:
            cutoff = datetime.now() - timedelta(days=days)
            daily = {}

            if self._format == "xml":
                records = self._get_xml_records("HKQuantityTypeIdentifierStepCount", days)
                for r in records:
                    date_key = r.get("endDate", "")[:10]
                    val = float(r.get("value", 0))
                    daily[date_key] = daily.get(date_key, 0) + val
            elif self._format == "json":
                metrics = self._json_data.get("data", {}).get("metrics", [])
                for metric in metrics:
                    if metric.get("name") == "step_count":
                        for point in metric.get("data", []):
                            date_str = point.get("date", "")[:10]
                            if date_str and datetime.fromisoformat(date_str) >= cutoff.replace(tzinfo=None):
                                daily[date_str] = daily.get(date_str, 0) + float(point.get("qty", 0))

            if not daily:
                return f"Aucune donnée de pas sur les {days} derniers jours."
            lines = [f"Pas quotidiens (derniers {days} jours):"]
            for date_key in sorted(daily.keys()):
                lines.append(f"  {date_key}: {int(daily[date_key]):,} pas")
            total = sum(daily.values())
            lines.append(f"Moyenne: {int(total / len(daily)):,} pas/jour")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur AppleHealth: {str(e)}"

    def get_sleep(self, days: int = 7) -> str:
        if not self._load_export():
            return EXPORT_INSTRUCTION if not APPLE_HEALTH_EXPORT_PATH else "Erreur AppleHealth: export introuvable dans le chemin spécifié."
        try:
            daily = {}

            if self._format == "xml":
                cutoff = datetime.now() - timedelta(days=days)
                for record in self._xml_root.iter("Record"):
                    if record.attrib.get("type") == "HKCategoryTypeIdentifierSleepAnalysis":
                        start_str = record.attrib.get("startDate", "")
                        end_str = record.attrib.get("endDate", "")
                        val = record.attrib.get("value", "")
                        if "Asleep" not in val and val != "HKCategoryValueSleepAnalysisAsleep":
                            continue
                        try:
                            start = datetime.strptime(start_str[:19], "%Y-%m-%d %H:%M:%S")
                            end = datetime.strptime(end_str[:19], "%Y-%m-%d %H:%M:%S")
                            if end >= cutoff:
                                date_key = end_str[:10]
                                duration_h = (end - start).total_seconds() / 3600
                                daily[date_key] = daily.get(date_key, 0) + duration_h
                        except ValueError:
                            pass
            elif self._format == "json":
                cutoff = datetime.now() - timedelta(days=days)
                metrics = self._json_data.get("data", {}).get("metrics", [])
                for metric in metrics:
                    if metric.get("name") in ("sleep_analysis", "sleep"):
                        for point in metric.get("data", []):
                            date_str = point.get("date", "")[:10]
                            if date_str and datetime.fromisoformat(date_str) >= cutoff.replace(tzinfo=None):
                                daily[date_str] = daily.get(date_str, 0) + float(point.get("qty", 0))

            if not daily:
                return f"Aucune donnée de sommeil sur les {days} derniers jours."
            lines = [f"Sommeil (derniers {days} jours):"]
            for date_key in sorted(daily.keys()):
                h = daily[date_key]
                lines.append(f"  {date_key}: {int(h)}h{int((h % 1) * 60):02d}")
            avg = sum(daily.values()) / len(daily)
            lines.append(f"Moyenne: {int(avg)}h{int((avg % 1) * 60):02d}/nuit")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur AppleHealth: {str(e)}"

    def get_heart_rate(self, days: int = 3) -> str:
        if not self._load_export():
            return EXPORT_INSTRUCTION if not APPLE_HEALTH_EXPORT_PATH else "Erreur AppleHealth: export introuvable dans le chemin spécifié."
        try:
            readings = []

            if self._format == "xml":
                records = self._get_xml_records("HKQuantityTypeIdentifierHeartRate", days)
                for r in records:
                    val = float(r.get("value", 0))
                    date = r.get("endDate", "")[:10]
                    readings.append((date, val))
            elif self._format == "json":
                cutoff = datetime.now() - timedelta(days=days)
                metrics = self._json_data.get("data", {}).get("metrics", [])
                for metric in metrics:
                    if metric.get("name") == "heart_rate":
                        for point in metric.get("data", []):
                            date_str = point.get("date", "")[:10]
                            if date_str and datetime.fromisoformat(date_str) >= cutoff.replace(tzinfo=None):
                                readings.append((date_str, float(point.get("Avg", point.get("qty", 0)))))

            if not readings:
                return f"Aucune donnée de fréquence cardiaque sur les {days} derniers jours."
            values = [v for _, v in readings]
            avg = sum(values) / len(values)
            min_hr = min(values)
            max_hr = max(values)
            return (
                f"Fréquence cardiaque (derniers {days} jours):\n"
                f"  Moyenne: {avg:.0f} bpm\n"
                f"  Min: {min_hr:.0f} bpm\n"
                f"  Max: {max_hr:.0f} bpm\n"
                f"  Mesures: {len(readings)}"
            )
        except Exception as e:
            return f"Erreur AppleHealth: {str(e)}"

    def get_activity_summary(self, days: int = 7) -> str:
        if not self._load_export():
            return EXPORT_INSTRUCTION if not APPLE_HEALTH_EXPORT_PATH else "Erreur AppleHealth: export introuvable dans le chemin spécifié."
        try:
            daily_calories = {}
            daily_exercise = {}

            if self._format == "xml":
                cal_records = self._get_xml_records("HKQuantityTypeIdentifierActiveEnergyBurned", days)
                for r in cal_records:
                    date_key = r.get("endDate", "")[:10]
                    daily_calories[date_key] = daily_calories.get(date_key, 0) + float(r.get("value", 0))
                ex_records = self._get_xml_records("HKQuantityTypeIdentifierAppleExerciseTime", days)
                for r in ex_records:
                    date_key = r.get("endDate", "")[:10]
                    daily_exercise[date_key] = daily_exercise.get(date_key, 0) + float(r.get("value", 0))
            elif self._format == "json":
                cutoff = datetime.now() - timedelta(days=days)
                metrics = self._json_data.get("data", {}).get("metrics", [])
                for metric in metrics:
                    name = metric.get("name", "")
                    for point in metric.get("data", []):
                        date_str = point.get("date", "")[:10]
                        if not date_str or datetime.fromisoformat(date_str) < cutoff.replace(tzinfo=None):
                            continue
                        if name in ("active_energy", "active_energy_burned"):
                            daily_calories[date_str] = daily_calories.get(date_str, 0) + float(point.get("qty", 0))
                        elif name == "apple_exercise_time":
                            daily_exercise[date_str] = daily_exercise.get(date_str, 0) + float(point.get("qty", 0))

            lines = [f"Résumé activité (derniers {days} jours):"]
            all_dates = sorted(set(list(daily_calories.keys()) + list(daily_exercise.keys())))
            if not all_dates:
                return "Aucune donnée d'activité trouvée."
            for date_key in all_dates:
                cal = daily_calories.get(date_key, 0)
                ex = daily_exercise.get(date_key, 0)
                lines.append(f"  {date_key}: {cal:.0f} kcal actives | {ex:.0f} min exercice")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur AppleHealth: {str(e)}"

    def get_weight(self, days: int = 30) -> str:
        if not self._load_export():
            return EXPORT_INSTRUCTION if not APPLE_HEALTH_EXPORT_PATH else "Erreur AppleHealth: export introuvable dans le chemin spécifié."
        try:
            readings = []

            if self._format == "xml":
                records = self._get_xml_records("HKQuantityTypeIdentifierBodyMass", days)
                for r in records:
                    val = float(r.get("value", 0))
                    unit = r.get("unit", "kg")
                    if "lb" in unit:
                        val = val * 0.453592
                    date = r.get("endDate", "")[:10]
                    readings.append((date, val))
            elif self._format == "json":
                cutoff = datetime.now() - timedelta(days=days)
                metrics = self._json_data.get("data", {}).get("metrics", [])
                for metric in metrics:
                    if metric.get("name") in ("body_mass", "weight"):
                        for point in metric.get("data", []):
                            date_str = point.get("date", "")[:10]
                            if date_str and datetime.fromisoformat(date_str) >= cutoff.replace(tzinfo=None):
                                readings.append((date_str, float(point.get("qty", 0))))

            if not readings:
                return f"Aucune donnée de poids sur les {days} derniers jours."
            readings.sort(key=lambda x: x[0])
            lines = [f"Historique poids (derniers {days} jours):"]
            for date_key, val in readings:
                lines.append(f"  {date_key}: {val:.1f} kg")
            if len(readings) > 1:
                diff = readings[-1][1] - readings[0][1]
                sign = "+" if diff > 0 else ""
                lines.append(f"Evolution: {sign}{diff:.1f} kg")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur AppleHealth: {str(e)}"
