import os
import asyncio
import pandas as pd
from scraper import query_icao_and_screenshot, calc_icao_methodology

# 設為 60，確保一次執行就能把所有「數值不一致的舊航線」與「缺少的反向航線」全部重刷完畢
MAX_ROUTES_PER_RUN = 60
HUB_ORIGINS = ["RCTP", "ZSPD", "ZSSS", "VHHH", "ZGSZ"]

async def main():
    os.makedirs("screenshots", exist_ok=True)
    dict_df = pd.read_csv("airports_dict.csv")
    cache_df = pd.read_csv("cache_db.csv")

    all_icaos = dict_df['icao'].dropna().unique().tolist()
    tasks_to_run = []
    existing_keys = set(cache_df['route_key'].astype(str).tolist())

    # 優先任務 1：揪出所有舊版公式算出來的假數據，以及與官方真值不符的航線，強制重刷！
    for idx, row in cache_df.iterrows():
        r_key = str(row['route_key'])
        orig = str(row['origin_icao']).strip().upper()
        dest = str(row['dest_icao']).strip().upper()
        img_path = f"screenshots/{r_key}.png"
        has_valid_img = os.path.exists(img_path) and os.path.getsize(img_path) > 5000

        curr_dist = int(round(float(row.get('distance_km', 0))))
        curr_fuel = int(round(float(row.get('fuel_burn_kg', 0))))

        # 判斷是否為舊版假公式算出來的數字 (舊公式: fuel = dist * 11.2 + 3780 或舊係數)
        is_fake_formula = (
            curr_dist == 0 or
            abs(curr_fuel - int(round(curr_dist * 11.2 + 3780))) <= 10 or
            (orig == "ZSPD" and dest == "VVNB" and curr_dist != 2309) or
            (orig == "VVNB" and dest == "ZSPD" and curr_dist != 2309) or
            (orig == "ZSPD" and dest == "RCTP" and curr_dist != 674)
        )

        if row.get('status') != 'Completed' or not has_valid_img or is_fake_formula:
            if (orig, dest, r_key) not in tasks_to_run:
                tasks_to_run.append((orig, dest, r_key))

    # 優先任務 2：全面掃描現有航線，找出所有「缺少反向回程」的項目，排入優先佇列
    existing_rows = cache_df.to_dict(orient='records')
    for row in existing_rows:
        orig = str(row['origin_icao']).strip().upper()
        dest = str(row['dest_icao']).strip().upper()
        rev_key = f"{dest}_{orig}_1KG"
        rev_img_path = f"screenshots/{rev_key}.png"
        has_valid_rev = os.path.exists(rev_img_path) and os.path.getsize(rev_img_path) > 5000

        if rev_key not in existing_keys or not has_valid_rev:
            if (dest, orig, rev_key) not in tasks_to_run:
                tasks_to_run.append((dest, orig, rev_key))

    # 優先任務 3：若還有名額，自動從主要樞紐雙向擴充新航線
    if len(tasks_to_run) < MAX_ROUTES_PER_RUN:
        for hub in HUB_ORIGINS:
            for dest in all_icaos:
                if hub != dest:
                    fwd_key = f"{hub}_{dest}_1KG"
                    rev_key = f"{dest}_{hub}_1KG"
                    
                    if fwd_key not in existing_keys and (hub, dest, fwd_key) not in tasks_to_run:
                        tasks_to_run.append((hub, dest, fwd_key))
                    if rev_key not in existing_keys and (dest, hub, rev_key) not in tasks_to_run:
                        tasks_to_run.append((dest, hub, rev_key))

                    if len(tasks_to_run) >= MAX_ROUTES_PER_RUN:
                        break
            if len(tasks_to_run) >= MAX_ROUTES_PER_RUN:
                break

    tasks_to_run = tasks_to_run[:MAX_ROUTES_PER_RUN]
    print(f"🚀 本次排程預計強制校準與雙向補齊共 {len(tasks_to_run)} 條航線: {[t[2] for t in tasks_to_run]}")

    for orig, dest, r_key in tasks_to_run:
        print(f"⏳ 正在產出官方憑證截圖與校準數據: {orig} -> {dest} ({r_key})...")
        res = await query_icao_and_screenshot(orig, dest, 1.0, r_key)
        
        if r_key in cache_df['route_key'].values:
            cache_df.loc[cache_df['route_key'] == r_key, ['distance_km', 'fuel_burn_kg', 'co2_per_kg', 'screenshot_file', 'status']] = [
                res['distance_km'], res['fuel_burn_kg'], res['co2_per_kg'], res['screenshot_file'], res['status']
            ]
        else:
            new_row = pd.DataFrame([res])
            for col in cache_df.columns:
                if col not in new_row.columns:
                    new_row[col] = ""
            new_row = new_row[cache_df.columns]
            cache_df = pd.concat([cache_df, new_row], ignore_index=True)

        cache_df.to_csv("cache_db.csv", index=False)
        print(f"✅ {r_key} 數據與截圖更新完成！ ({res['distance_km']} KM / {res['fuel_burn_kg']} KG / {res['co2_per_kg']} KG)")

if __name__ == "__main__":
    asyncio.run(main())
