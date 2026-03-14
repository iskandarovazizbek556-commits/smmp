# api/providers.py
import requests
from config import Config

def fetch_services():
    """
    1xPanel API'dan xizmatlarni olish
    """
    url = f"{Config.PROVIDER_URL}?action=services&key={Config.PROVIDER_KEY}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"error": str(e)}

    if not isinstance(data, list) or len(data) == 0:
        return {"error": "Xizmatlar topilmadi yoki API bo‘sh"}

    services = []
    for s in data:
        services.append({
            "service_id": int(s.get("service", 0)),
            "name": s.get("name", ""),
            "category": s.get("category", "General"),
            "type": s.get("type", ""),
            "rate": float(s.get("rate", 0)),
            "min": int(s.get("min", 0)),
            "max": int(s.get("max", 0)),
            "description": s.get("description", "")
        })
    return services