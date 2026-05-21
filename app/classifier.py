import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

SHOPPING_KEYWORDS = {
    "ca": [
        "comprar", "compra", "llista", "supermercat", "botiga", "mercat",
        "llet", "pa", "ous", "fruita", "verdura", "carn", "peix",
        "arròs", "pasta", "tomàquet", "enciam", "formatge", "pollastre",
        "aigua", "vi", "cervesa", "sucre", "farina", "oli", "sal",
        "sabó", "paper", "iogurt", "galetes", "cafè", "te",
        "xocolata", "mantega", "patates", "ceba", "all",
        "pastanaga", "poma", "plàtan", "taronja", "llimona",
    ],
    "es": [
        "comprar", "compra", "lista", "supermercado", "tienda", "mercado",
        "leche", "pan", "huevos", "fruta", "verdura", "carne", "pescado",
        "arroz", "pasta", "tomate", "lechuga", "queso", "pollo",
    ],
}

APPOINTMENT_KEYWORDS = {
    "ca": [
        "metge", "doctor", "cita", "visita", "consulta", "hospital",
        "clínica", "medicina", "revisió", "anàlisi", "especialista",
        "dentista", "oftalmòleg", "cardiòleg", "urgència", "capsalera",
        "radiografia", "ecografia", "operació", "cirurgia",
        "vacuna", "medicació", " recepta", "infermer",
    ],
    "es": [
        "médico", "doctor", "cita", "visita", "consulta", "hospital",
        "clínica", "medicina", "revisión", "análisis", "especialista",
        "dentista", "oftalmólogo", "cardiólogo", "urgencia",
    ],
}

RELATIVE_DAYS = {
    "ca": {
        "avui": 0, "demà": 1, "demà passat": 2, "passat demà": 2,
        "ahir": -1,
    },
    "es": {
        "hoy": 0, "mañana": 1, "pasado mañana": 2, "ayer": -1,
    },
}

WEEKDAYS = {
    "ca": {
        "dilluns": 0, "dimarts": 1, "dimecres": 2, "dijous": 3,
        "divendres": 4, "dissabte": 5, "diumenge": 6,
    },
    "es": {
        "lunes": 0, "martes": 1, "miércoles": 2, "jueves": 3,
        "viernes": 4, "sábado": 5, "domingo": 6,
    },
}


class ClassificationResult:
    def __init__(self, category: str, text: str, entities: dict):
        self.category = category
        self.text = text
        self.entities = entities


class Classifier:
    def __init__(self, language: str = "ca"):
        self.language = language
        self.shopping_words = SHOPPING_KEYWORDS.get(language, SHOPPING_KEYWORDS["ca"])
        self.appointment_words = APPOINTMENT_KEYWORDS.get(language, APPOINTMENT_KEYWORDS["ca"])
        self.relative_days = RELATIVE_DAYS.get(language, RELATIVE_DAYS["ca"])
        self.weekdays = WEEKDAYS.get(language, WEEKDAYS["ca"])

    def classify(self, text: str) -> ClassificationResult:
        text_lower = text.lower().strip()

        shopping_score = sum(1 for w in self.shopping_words if w in text_lower)
        appointment_score = sum(1 for w in self.appointment_words if w in text_lower)

        logger.info(f"Scores - compra: {shopping_score}, cita: {appointment_score}")

        if appointment_score > shopping_score:
            return self._extract_appointment(text)
        else:
            return self._extract_shopping(text)

    def _extract_shopping(self, text: str) -> ClassificationResult:
        return ClassificationResult("shopping", text, {"items": [text.strip()]})

    def _extract_appointment(self, text: str) -> ClassificationResult:
        parsed_date = self._parse_datetime(text)
        place = self._extract_place(text)
        doctor = self._extract_doctor(text)

        return ClassificationResult("appointment", text, {
            "summary": text.strip(),
            "date": parsed_date,
            "place": place,
            "doctor": doctor,
        })

    def _parse_datetime(self, text: str):
        today = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)

        for rel_word, days in self.relative_days.items():
            if rel_word in text.lower():
                return today + timedelta(days=days)

        for day_name, days_offset in self.weekdays.items():
            if day_name in text.lower():
                today_weekday = today.weekday()
                diff = (days_offset - today_weekday) % 7
                if diff == 0:
                    diff = 7
                return today + timedelta(days=diff)

        time_match = re.search(r'(\d{1,2})[.:](\d{2})\s*(h)?', text)
        date_match = re.search(r'(\d{1,2})[./](\d{1,2})([./](\d{2,4}))?', text)

        if date_match:
            day, month = int(date_match.group(1)), int(date_match.group(2))
            year_str = date_match.group(4)
            year = int(year_str) if year_str else today.year
            result = today.replace(month=month, day=day, hour=9, minute=0)
            if time_match:
                result = result.replace(hour=int(time_match.group(1)), minute=int(time_match.group(2)))
            return result

        if time_match:
            return today.replace(hour=int(time_match.group(1)), minute=int(time_match.group(2)))

        return None

    def _extract_place(self, text: str):
        known_places = ["hospital", "clínica", "consultori", "cap", "ambulatori", "centre"]
        for word in known_places:
            if word in text.lower():
                return word.capitalize()
        return None

    def _extract_doctor(self, text: str):
        match = re.search(r'(?:Dr\.?|Doctor[a]?|Dra\.?)\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*)', text)
        if match:
            return match.group(1)
        return None
