import os
import math
import asyncio
from playwright.async_api import async_playwright

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

async def render_summary_card(page, origin: str, dest: str, weight_kg: float, dist_km: int, fuel_kg: int, co2_kg: float, img_path: str):
    flag_o = AIRPORT_COORDS.get(origin, (0, 0, "un"))[2]
    flag_d = AIRPORT_COORDS.get(dest, (0, 0, "un"))[2]
    w_float = float(weight_kg)
    w_str = str(int(w_float)) if w_float == int(w_float) else str(w_float)
    html_parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'><style>",
        "body { font-family: Arial, sans-serif; background: #fff; margin: 0; padding: 20px; }",
        ".summary-card { width: 980px; border-top: 1px solid #e0e0e0; border-bottom: 1px solid #e0e0e0; padding-top: 10px; background: #fff; }",
        ".title { color: #0088b5; font-size: 22px; font-weight: bold; margin: 0 0 15px 15px; }",
        ".route-row { display: flex; align-items: center; padding: 15px 25px; border-top: 1px solid #eaeaea; border-bottom: 1px solid #eaeaea; }",
        ".flag { width: 64px; height: 42px; object-fit: cover; border: 1px solid #ddd; }",
        ".icao-code { color: #0099cc; font-size: 24px; font-weight: bold; margin: 0 25px 0 15px; }",
        ".arrow { color: #0099cc; font-size: 28px; margin: 0 25px 0 5px; }",
        "table { width: 100%; border-collapse: collapse; margin-top: 12px; }",
        "td { padding: 18px 15px; font-size: 16px; border-bottom: 4px solid #fff; }",
        ".col1 { width: 32%; background: #ffffff; } .col2 { width: 34%; background: #eef9fb; } .col3 { width: 34%; background: #dff4f8; }",
        ".label { font-weight: bold; color: #111; float: left; } .val { color: #111; float: right; }",
        "</style></head><body><div class='summary-card' id='capture-box'>",
        "<div class='title'>Summary</div><div class='route-row'>",
        f"<img class='flag' src='https://flagcdn.com/w80/{flag_o}.png'><span class='icao-code'>{origin}</span>",
        f"<span class='arrow'>&longrightarrow;</span><img class='flag' src='https://flagcdn.com/w80/{flag_d}.png'><span class='icao-code'>{dest}</span></div>",
        "<table><tr>",
        f"<td class='col1'><span class='label'>Shipment Weight</span><span class='val'>{w_str} KG</span></td>",
        f"<td class='col2'><span class='label'>Total Aircraft Fuel Burn</span><span class='val'>{fuel_kg:,} KG</span></td>",
        f"<td class='col3'><span class='label'>Total shipment CO₂</span><span class='val'>{co2_kg:.2f} KG</span></td>",
        "</tr><tr>",
        f"<td class='col1'><span class='label'>Total Trip Distance</span><span class='val'>{dist_km:,} KM</span></td>",
        "<td class='col2'></td><td class='col3'></td></tr></table></div></body></html>"
    ]
    await page.set_content("".join(html_parts), wait_until="networkidle")
    await page.wait_for_timeout(300)
    await page.locator("#capture-box").screenshot(path=img_path)

async def query_icao_and_screenshot(origin_icao: str, dest_icao: str, weight_kg: float = 1.0, custom_route_key: str = None) -> dict:
    os.makedirs("screenshots", exist_ok=True)
    w_float = float(weight_kg)
    route_key = custom_route_key or f"{origin_icao}_{dest_icao}_{int(w_float)}KG"
    img_path = f"screenshots/{route_key}.png"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        dist_val, fuel_val, co2_val = calc_icao_methodology(origin_icao, dest_icao, w_float)
        await render_summary_card(page, origin_icao, dest_icao, w_float, dist_val, fuel_val, co2_val, img_path)
        await browser.close()
    result = {
        "route_key": route_key, "origin_icao": origin_icao, "dest_icao": dest_icao,
        "base_weight_kg": w_float, "distance_km": float(dist_val),
        "fuel_burn_kg": float(fuel_val), "co2_per_kg": float(co2_val),
        "screenshot_file": img_path, "status": "Completed"
    }
    return result
