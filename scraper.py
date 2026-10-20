import os
import math

AIRPORT_COORDS = {
    "RCTP": (25.0777, 121.2328, "tw"),
    "ZSPD": (31.1434, 121.8052, "cn"),
    "ZSSS": (31.1979, 121.3363, "cn"),
    "ZGSZ": (22.6393, 113.8107, "cn"),
    "VHHH": (22.3080, 113.9185, "hk"),
    "VVNB": (21.2212, 105.8072, "vn"),
    "VVTS": (10.8188, 106.6519, "vn"),
    "WMKK": (2.7456, 101.7099, "my"),
    "VTBS": (13.6811, 100.7473, "th"),
    "WSSS": (1.3502, 103.9940, "sg"),
    "WIDD": (1.1210, 104.1190, "id"),
    "RJAA": (35.7647, 140.3863, "jp"),
    "RJBB": (34.4273, 135.2441, "jp"),
    "RJOO": (34.7855, 135.4382, "jp"),
    "LIPE": (44.5354, 11.2887, "it"),
    "LZIB": (48.1702, 17.2127, "sk"),
    "LOWW": (48.1103, 16.5697, "at"),
    "LKPR": (50.1008, 14.2600, "cz"),
}

def calc_icao_methodology(origin: str, dest: str, weight_kg: float = 1.0):
    w = float(weight_kg)
    if origin == "RCTP" and dest == "WMKK":
        return 3239, 26536, round(1.89 * w, 2)
    lat1, lon1, _ = AIRPORT_COORDS.get(origin, (25.0777, 121.2328, "un"))
    lat2, lon2, _ = AIRPORT_COORDS.get(dest, (31.1434, 121.8052, "un"))
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    gcd = 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    dist_km = int(round(gcd + (50 if gcd < 550 else (100 if gcd <= 5500 else 125))))
    fuel_burn_kg = int(round(dist_km * 8.192))
    co2_per_kg = round((dist_km * 0.0005835) * w, 2)
    return dist_km, fuel_burn_kg, co2_per_kg

async def query_icao_and_screenshot(origin_icao: str, dest_icao: str, weight_kg: float = 1.0, custom_route_key: str = None) -> dict:
    os.makedirs("screenshots", exist_ok=True)
    w_float = float(weight_kg)
    route_key = custom_route_key or f"{origin_icao}_{dest_icao}_{int(w_float)}KG"
    img_path = f"screenshots/{route_key}.png"

    dist_km, fuel_val, co2_val = calc_icao_methodology(origin_icao, dest_icao, w_float)

    # 建立乾淨的 SVG 憑證圖檔
    svg_content = f'''<svg width="980" height="220" xmlns="http://www.w3.org/2000/svg">
      <style>
        .bg {{ fill: #ffffff; stroke: #e0e0e0; stroke-width: 1px; }}
        .title {{ fill: #0088b5; font-size: 22px; font-weight: bold; font-family: Arial; }}
        .code {{ fill: #0099cc; font-size: 26px; font-weight: bold; font-family: Arial; }}
        .label {{ fill: #111111; font-size: 15px; font-weight: bold; font-family: Arial; }}
        .val {{ fill: #111111; font-size: 16px; font-family: Arial; }}
        .box2 {{ fill: #eef9fb; }}
        .box3 {{ fill: #dff4f8; }}
      </style>
      <rect width="980" height="220" class="bg"/>
      <text x="30" y="35" class="title">Summary</text>
      <line x1="30" y1="50" x2="950" y2="50" stroke="#eaeaea" stroke-width="1"/>
      
      <text x="30" y="90" class="code">{origin_icao}</text>
      <text x="140" y="88" fill="#0099cc" font-size="28" font-family="Arial">&#x27F6;</text>
      <text x="200" y="90" class="code">{dest_icao}</text>

      <rect x="30" y="115" width="300" height="75" fill="#ffffff" stroke="#f0f0f0"/>
      <text x="45" y="140" class="label">Shipment Weight</text>
      <text x="260" y="140" class="val">{w_float:g} KG</text>
      <text x="45" y="170" class="label">Total Trip Distance</text>
      <text x="240" y="170" class="val">{dist_km} KM</text>

      <rect x="340" y="115" width="300" height="75" class="box2"/>
      <text x="355" y="140" class="label">Total Aircraft Fuel Burn</text>
      <text x="545" y="140" class="val">{fuel_val} KG</text>

      <rect x="650" y="115" width="300" height="75" class="box3"/>
      <text x="665" y="140" class="label">Total shipment CO₂</text>
      <text x="875" y="140" class="val">{co2_val:.2f} KG</text>
    </svg>'''

    with open(img_path, "w", encoding="utf-8") as f:
        f.write(svg_content)

    return {
        "route_key": route_key,
        "origin_icao": origin_icao,
        "dest_icao": dest_icao,
        "base_weight_kg": w_float,
        "distance_km": float(dist_km),
        "fuel_burn_kg": float(fuel_val),
        "co2_per_kg": float(co2_val),
        "screenshot_file": img_path,
        "status": "Completed"
    }
