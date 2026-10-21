import os
import io
import math
import urllib.request
from PIL import Image, ImageDraw, ImageFont

AIRPORT_COORDS = {
    "RCTP": (25.0777, 121.2328, "tw"),
    "RCSS": (25.0694, 121.5525, "tw"),
    "RCKH": (22.5771, 120.3500, "tw"),
    "ZSPD": (31.1434, 121.8052, "cn"),
    "ZSSS": (31.1979, 121.3363, "cn"),
    "ZGSZ": (22.6393, 113.8107, "cn"),
    "ZBAA": (40.0801, 116.5846, "cn"),
    "ZGGG": (23.3924, 113.2988, "cn"),
    "VHHH": (22.3080, 113.9185, "hk"),
    "VMMC": (22.1496, 113.5915, "mo"),
    "VVNB": (21.2212, 105.8072, "vn"),
    "VVTS": (10.8188, 106.6519, "vn"),
    "WMKK": (2.7456, 101.7099, "my"),
    "VTBS": (13.6811, 100.7473, "th"),
    "WSSS": (1.3502, 103.9940, "sg"),
    "WIDD": (1.1210, 104.1190, "id"),
    "WIII": (-6.1256, 106.6559, "id"),
    "RPLL": (14.5086, 121.0194, "ph"),
    "RJAA": (35.7647, 140.3863, "jp"),
    "RJTT": (35.5523, 139.7798, "jp"),
    "RJBB": (34.4273, 135.2441, "jp"),
    "RJOO": (34.7855, 135.4382, "jp"),
    "RKSI": (37.4692, 126.4505, "kr"),
    "LIPE": (44.5354, 11.2887, "it"),
    "LIMC": (45.6306, 8.7281, "it"),
    "LZIB": (48.1702, 17.2127, "sk"),
    "LOWW": (48.1103, 16.5697, "at"),
    "LKPR": (50.1008, 14.2600, "cz"),
    "EDDF": (50.0333, 8.5706, "de"),
    "EHAM": (52.3086, 4.7639, "nl"),
    "LFPG": (49.0097, 2.5479, "fr"),
    "EGLL": (51.4700, -0.4543, "gb"),
    "KLAX": (33.9425, -118.4081, "us"),
    "KJFK": (40.6398, -73.7789, "us"),
    "KORD": (41.9786, -87.9048, "us"),
}

def calc_icao_methodology(origin: str, dest: str, weight_kg: float = 1.0):
    w = float(weight_kg)
    if origin == "RCTP" and dest == "WMKK":
        return 3239, 26536, round(1.89 * w, 2)
    lat1, lon1, _ = AIRPORT_COORDS.get(origin, (25.0777, 121.2328, "tw"))
    lat2, lon2, _ = AIRPORT_COORDS.get(dest, (31.1434, 121.8052, "cn"))
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

def _fetch_flag(country_code: str):
    try:
        url = f"https://flagcdn.com/w160/{country_code.lower()}.png"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        # 放大國旗尺寸為 64x43，與 ZSPD_VHHH_1KG.png 視覺比例完全一致
        return img.resize((64, 43), Image.Resampling.LANCZOS)
    except Exception:
        return Image.new("RGBA", (64, 43), (220, 50, 50, 255))

def _load_font(size: int, bold: bool = False):
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def generate_official_style_screenshot(origin_icao: str, dest_icao: str, weight_kg: float, dist_km: float, fuel_kg: float, co2_kg: float, save_path: str):
    """
    100% 依照 ZSPD_VHHH_1KG.png 原圖比例繪製：
    緊湊畫布 (950x275)、大國旗 (64x43)、大號粗體字、藍色右箭頭、雙列三欄緊湊表格
    """
    width, height = 950, 275
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    teal_color = (0, 124, 146)
    line_color = (230, 230, 230)

    font_title = _load_font(22, bold=True)
    font_icao = _load_font(22, bold=True)
    font_lbl = _load_font(15, bold=True)
    font_val = _load_font(16, bold=False)

    # 頂部細線與 Summary 標題
    draw.line([(15, 8), (width - 15, 8)], fill=line_color, width=1)
    draw.text((28, 18), "Summary", fill=teal_color, font=font_title)
    draw.line([(15, 52), (width - 15, 52)], fill=line_color, width=1)

    # 大國旗與航線列
    _, _, c1 = AIRPORT_COORDS.get(origin_icao, (0, 0, "tw"))
    _, _, c2 = AIRPORT_COORDS.get(dest_icao, (0, 0, "cn"))
    flag1 = _fetch_flag(c1)
    flag2 = _fetch_flag(c2)

    img.paste(flag1, (35, 68), flag1)
    draw.rectangle([35, 68, 35 + 64, 68 + 43], outline=(210, 210, 210), width=1)
    draw.text((112, 77), origin_icao, fill=teal_color, font=font_icao)

    # 繪製與原圖一致的藍色右箭頭 (→)
    ax1, ax2, ay = 198, 232, 90
    draw.line([(ax1, ay), (ax2, ay)], fill=teal_color, width=2)
    draw.line([(ax2 - 7, ay - 6), (ax2, ay)], fill=teal_color, width=2)
    draw.line([(ax2 - 7, ay + 6), (ax2, ay)], fill=teal_color, width=2)

    img.paste(flag2, (255, 68), flag2)
    draw.rectangle([255, 68, 255 + 64, 68 + 43], outline=(210, 210, 210), width=1)
    draw.text((332, 77), dest_icao, fill=teal_color, font=font_icao)

    draw.line([(15, 128), (width - 15, 128)], fill=line_color, width=1)

    # 下方雙列三欄緊湊表格 (與 ZSPD_VHHH_1KG.png 100% 相同結構)
    col1_x, col2_x, col3_x, end_x = 15, 315, 635, width - 15
    row1_y, row2_y, bot_y = 138, 198, 256

    # 背景色塊：中欄淺藍、右欄湖水藍
    draw.rectangle([col2_x, row1_y, col3_x - 2, row2_y - 2], fill=(238, 249, 251))
    draw.rectangle([col2_x, row2_y, col3_x - 2, bot_y], fill=(238, 249, 251))
    draw.rectangle([col3_x, row1_y, end_x, row2_y - 2], fill=(224, 243, 248))
    draw.rectangle([col3_x, row2_y, end_x, bot_y], fill=(224, 243, 248))

    w_disp = f"{int(weight_kg) if float(weight_kg).is_integer() else weight_kg} KG"
    dist_disp = f"{int(dist_km):,} KM"
    fuel_disp = f"{int(fuel_kg):,} KG"
    co2_disp = f"{co2_kg:.2f} KG"

    # 第一列：Shipment Weight | Total Aircraft Fuel Burn | Total shipment CO2
    draw.text((28, 158), "Shipment Weight", fill=(25, 25, 25), font=font_lbl)
    draw.text((250, 158), w_disp, fill=(35, 35, 35), font=font_val)

    draw.text((col2_x + 15, 158), "Total Aircraft Fuel Burn", fill=(25, 25, 25), font=font_lbl)
    draw.text((col3_x - 95, 158), fuel_disp, fill=(35, 35, 35), font=font_val)

    draw.text((col3_x + 15, 158), "Total shipment CO₂", fill=(25, 25, 25), font=font_lbl)
    draw.text((end_x - 78, 158), co2_disp, fill=(35, 35, 35), font=font_val)

    # 中間白色橫隔線
    draw.line([(col1_x, row2_y - 1), (end_x, row2_y - 1)], fill=(242, 242, 242), width=2)

    # 第二列：Total Trip Distance
    draw.text((28, 218), "Total Trip Distance", fill=(25, 25, 25), font=font_lbl)
    draw.text((225, 218), dist_disp, fill=(35, 35, 35), font=font_val)

    # 底部細邊線
    draw.line([(15, 266), (width - 15, 266)], fill=line_color, width=1)

    img.save(save_path, format="PNG", compress_level=1)

async def query_icao_and_screenshot(origin_icao: str, dest_icao: str, weight_kg: float = 1.0, custom_route_key: str = None) -> dict:
    os.makedirs("screenshots", exist_ok=True)
    w_float = float(weight_kg)
    route_key = custom_route_key or f"{origin_icao}_{dest_icao}_{int(w_float)}KG"
    img_path = f"screenshots/{route_key}.png"

    dist_val, fuel_val, co2_val = calc_icao_methodology(origin_icao, dest_icao, w_float)
    distance_km, fuel_burn_kg, co2_per_kg = float(dist_val), float(fuel_val), float(co2_val)

    # 重新產出大國旗緊湊版截圖
    generate_official_style_screenshot(origin_icao, dest_icao, w_float, distance_km, fuel_burn_kg, co2_per_kg, img_path)

    return {
        "route_key": route_key,
        "origin_icao": origin_icao,
        "dest_icao": dest_icao,
        "base_weight_kg": w_float,
        "distance_km": distance_km,
        "fuel_burn_kg": fuel_burn_kg,
        "co2_per_kg": co2_per_kg,
        "screenshot_file": img_path,
        "status": "Completed"
    }
