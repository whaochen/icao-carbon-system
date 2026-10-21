import os
import asyncio
import pandas as pd
from scraper import query_icao_and_screenshot

MAX_ROUTES_PER_RUN = 5
HUB_ORIGINS = ["RCTP", "ZSPD", "ZSSS", "VHHH", "ZGSZ"]

async def main():
    os.makedirs("screenshots", exist_ok=True)
    dict_df = pd.read_csv("airports_dict.csv")
    cache_df = pd.read_csv("cache_db.csv")

    all_icaos = dict_df['icao'].dropna().unique().tolist()
    tasks_to_run = []
    existing_keys = set(cache_df['route_key'].astype(str).tolist())

    # 1. 檢查現有資料庫：是否有缺圖或未完成的航線
    for idx, row in cache_df.iterrows():
        r_key = str(row['route_key'])
        orig = str(row['origin_icao'])
        dest = str(row['dest_icao'])
        img_path = f"screenshots/{r_key}.png"
        has_valid_img = os.path.exists(img_path) and os.path.getsize(img_path) > 10000

        if row.get('status') != 'Completed' or not has_valid_img:
            tasks_to_run.append((orig, dest, r_key))
            # 同時確保反向航線也被加入
            rev_key = f"{dest}_{orig}_1KG"
            if rev_key not in existing_keys:
                tasks_to_run.append((dest, orig, rev_key))

    # 2. 自動探索新航線：每次自動擴充時，同時建立「正向與反向」雙向截圖
    if len(tasks_to_run) < MAX_ROUTES_PER_RUN:
        for hub in HUB_ORIGINS:
            for dest in all_icaos:
                if hub != dest:
                    fwd_key = f"{hub}_{dest}_1KG"
                    rev_key = f"{dest}_{hub}_1KG"
                    
                    # 檢查正向
                    if fwd_key not in existing_keys and (hub, dest, fwd_key) not in tasks_to_run:
                        tasks_to_run.append((hub, dest, fwd_key))
                    # 檢查反向（雙向同步建檔）
                    if rev_key not in existing_keys and (dest, hub, rev_key) not in tasks_to_run:
                        tasks_to_run.append((dest, hub, rev_key))

                    if len(tasks_to_run) >= MAX_ROUTES_PER_RUN:
                        break
            if len(tasks_to_run) >= MAX_ROUTES_PER_RUN:
                break

    tasks_to_run = tasks_to_run[:MAX_ROUTES_PER_RUN]
    print(f"🚀 本次排程預計自動抓取雙向航線截圖: {[t[2] for t in tasks_to_run]}")

    for orig, dest, r_key in tasks_to_run:
        print(f"⏳ 正在產出官方憑證截圖: {orig} -> {dest} ({r_key})...")
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
        print(f"✅ {r_key} 雙向對稱建檔完成！")

if __name__ == "__main__":
    asyncio.run(main())
