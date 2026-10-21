import os
import asyncio
import pandas as pd
from scraper import query_icao_and_screenshot, calc_icao_methodology

MAX_ROUTES_PER_RUN = 60
HUB_ORIGINS = ["RCTP", "ZSPD", "ZSSS", "VHHH", "ZGSZ"]

async def main():
    os.makedirs("screenshots", exist_ok=True)
    dict_df = pd.read_csv("airports_dict.csv")
    cache_df = pd.read_csv("cache_db.csv")

    all_icaos = dict_df['icao'].dropna().unique().tolist()
    tasks_to_run = []
    existing_keys = set(cache_df['route_key'].astype(str).tolist())

    # 1. 檢查現有快取與官方真值的差異（正確接收 3 個變數）
    for idx, row in cache_df.iterrows():
        r_key = str(row['route_key'])
        orig = str(row['origin_icao']).strip().upper()
        dest = str(row['dest_icao']).strip().upper()
        img_path = f"screenshots/{r_key}.png"
        has_valid_img = os.path.exists(img_path) and os.path.getsize(img_path) > 5000

        # 正確以 3 個變數接收 calc_icao_methodology 的回傳值
        exp_dist, exp_fuel, exp_co2 = calc_icao_methodology(orig, dest, 1.0)
        curr_dist = int(round(float(row.get('distance_km', 0))))
        curr_fuel = int(round(float(row.get('fuel_burn_kg', 0))))

        if (row.get('status') != 'Completed' or 
            not has_valid_img or 
            curr_dist != exp_dist or 
            curr_fuel != exp_fuel):
            if (orig, dest, r_key) not in tasks_to_run:
                tasks_to_run.append((orig, dest, r_key))

    # 2. 檢查反向回程是否補齊
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

    # 3. 擴充新航線
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
    print(f"🚀 本次排程預計執行: {[t[2] for t in tasks_to_run]}")

    for orig, dest, r_key in tasks_to_run:
        print(f"⏳ 正在處理: {orig} -> {dest} ({r_key})...")
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
        print(f"✅ {r_key} 完成！")

if __name__ == "__main__":
    asyncio.run(main())
