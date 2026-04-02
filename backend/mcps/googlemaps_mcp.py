import os

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


class GoogleMapsMCP:
    def __init__(self):
        self._client = None

    def _ensure_connected(self):
        if not self._client:
            if not GOOGLE_MAPS_API_KEY:
                return False
            import googlemaps
            self._client = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)
        return True

    def get_directions(self, origin: str, destination: str, mode: str = "driving") -> str:
        if not self._ensure_connected():
            return "Erreur GoogleMaps: GOOGLE_MAPS_API_KEY manquant."
        try:
            valid_modes = {"driving", "walking", "bicycling", "transit"}
            if mode not in valid_modes:
                mode = "driving"
            results = self._client.directions(origin, destination, mode=mode)
            if not results:
                return f"Aucun itinéraire trouvé de '{origin}' à '{destination}'."
            route = results[0]
            leg = route["legs"][0]
            distance = leg["distance"]["text"]
            duration = leg["duration"]["text"]
            start = leg["start_address"]
            end = leg["end_address"]
            steps = leg.get("steps", [])
            lines = [
                f"Itinéraire ({mode}): {start} → {end}",
                f"Distance: {distance} | Durée: {duration}",
                f"Étapes ({len(steps)}):",
            ]
            for i, step in enumerate(steps[:8], 1):
                import re
                instruction = re.sub(r"<[^>]+>", "", step.get("html_instructions", ""))
                step_distance = step.get("distance", {}).get("text", "")
                lines.append(f"  {i}. {instruction} ({step_distance})")
            if len(steps) > 8:
                lines.append(f"  ... et {len(steps) - 8} étapes supplémentaires")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur GoogleMaps: {str(e)}"

    def get_travel_time(self, origin: str, destination: str, mode: str = "driving") -> str:
        if not self._ensure_connected():
            return "Erreur GoogleMaps: GOOGLE_MAPS_API_KEY manquant."
        try:
            valid_modes = {"driving", "walking", "bicycling", "transit"}
            if mode not in valid_modes:
                mode = "driving"
            results = self._client.distance_matrix(origin, destination, mode=mode)
            rows = results.get("rows", [])
            if not rows:
                return f"Impossible de calculer la durée de '{origin}' à '{destination}'."
            element = rows[0]["elements"][0]
            if element.get("status") != "OK":
                return f"Itinéraire introuvable (status: {element.get('status')})."
            duration = element["duration"]["text"]
            distance = element["distance"]["text"]
            return f"Durée ({mode}): {duration} | Distance: {distance}"
        except Exception as e:
            return f"Erreur GoogleMaps: {str(e)}"

    def search_places(self, query: str, location: str = "", radius: int = 5000) -> str:
        if not self._ensure_connected():
            return "Erreur GoogleMaps: GOOGLE_MAPS_API_KEY manquant."
        try:
            kwargs = {"query": query}
            if location:
                geocode = self._client.geocode(location)
                if geocode:
                    loc = geocode[0]["geometry"]["location"]
                    kwargs["location"] = (loc["lat"], loc["lng"])
                    kwargs["radius"] = radius
            results = self._client.places(**kwargs)
            places = results.get("results", [])
            if not places:
                return f"Aucun lieu trouvé pour '{query}'."
            lines = [f"Lieux pour '{query}':"]
            for p in places[:8]:
                name = p.get("name", "?")
                address = p.get("formatted_address", p.get("vicinity", ""))
                rating = p.get("rating", "")
                place_id = p.get("place_id", "")
                rating_str = f" | Note: {rating}/5" if rating else ""
                lines.append(f"  {name} | {address}{rating_str} | id: {place_id}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur GoogleMaps: {str(e)}"

    def get_place_details(self, place_id: str) -> str:
        if not self._ensure_connected():
            return "Erreur GoogleMaps: GOOGLE_MAPS_API_KEY manquant."
        try:
            result = self._client.place(place_id)
            p = result.get("result", {})
            if not p:
                return f"Aucun détail trouvé pour place_id: {place_id}"
            name = p.get("name", "?")
            address = p.get("formatted_address", "?")
            phone = p.get("formatted_phone_number", "N/A")
            website = p.get("website", "N/A")
            rating = p.get("rating", "N/A")
            reviews_count = p.get("user_ratings_total", 0)
            hours = p.get("opening_hours", {}).get("weekday_text", [])
            lines = [
                f"Lieu: {name}",
                f"Adresse: {address}",
                f"Téléphone: {phone}",
                f"Site web: {website}",
                f"Note: {rating}/5 ({reviews_count} avis)",
            ]
            if hours:
                lines.append("Horaires:")
                for h in hours:
                    lines.append(f"  {h}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur GoogleMaps: {str(e)}"

    def geocode(self, address: str) -> str:
        if not self._ensure_connected():
            return "Erreur GoogleMaps: GOOGLE_MAPS_API_KEY manquant."
        try:
            results = self._client.geocode(address)
            if not results:
                return f"Adresse introuvable: '{address}'"
            r = results[0]
            loc = r["geometry"]["location"]
            formatted = r.get("formatted_address", address)
            return (
                f"Adresse: {formatted}\n"
                f"Latitude: {loc['lat']}\n"
                f"Longitude: {loc['lng']}"
            )
        except Exception as e:
            return f"Erreur GoogleMaps: {str(e)}"

    def reverse_geocode(self, lat: float, lng: float) -> str:
        if not self._ensure_connected():
            return "Erreur GoogleMaps: GOOGLE_MAPS_API_KEY manquant."
        try:
            results = self._client.reverse_geocode((lat, lng))
            if not results:
                return f"Aucune adresse trouvée pour ({lat}, {lng})."
            r = results[0]
            formatted = r.get("formatted_address", "?")
            components = r.get("address_components", [])
            city = next((c["long_name"] for c in components if "locality" in c.get("types", [])), "")
            country = next((c["long_name"] for c in components if "country" in c.get("types", [])), "")
            lines = [f"Coordonnées: ({lat}, {lng})", f"Adresse: {formatted}"]
            if city:
                lines.append(f"Ville: {city}")
            if country:
                lines.append(f"Pays: {country}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur GoogleMaps: {str(e)}"
