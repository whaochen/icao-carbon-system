import os
import asyncio
import pandas as pd
from scraper import query_icao_and_screenshot

# 每次排程最多自動抓取幾條航線（避免單次執行過久被 ICAO 官網阻擋）
MAX_ROUTES_PER_RUN = 5

# 主要出發樞紐機場（自動優先為這些起點擴充熱門航線截圖）
HUB_ORIGINS = ["RCTP", "ZSPD", "ZSSS", "VHHH", "ZGSZ"]

async def main():
    os.makedirs("screenshots", exist_ok=True)
    dict_df = pd.read_csv("airports_dict.csv")
    cache_df = pd.read_csv("cache_db.csv")

    all_icaos = dict_df['icao'].dropna().unique().tolist()
    tasks_to_run = []

    # 1. 優先檢查現有 cache_db.csv：如果是 Pending，或者雖然是 Completed 但卻沒有真實圖檔 (<10KB)，一律排入重抓！
    for idx, row in cache_df.iterrows():
        r_key = str(row['route_key'])
        orig = str(row['origin_icao'])
        dest = str(row['dest_icao'])
        img_path = f"screenshots/{r_key}.png"
        has_valid_img = os.path.exists(img_path) and os.path.getsize(img_path) > 10000

        if row.get('status') != 'Completed' or not has_valid_img:
            tasks_to_run.append((orig, dest, r_key))

    # 2. 如果現有清單都齊全了，自動從機場字典組合出「尚未建檔的新航線」來擴充圖庫！
    existing_keys = set(cache_df['route_key'].astype(str).tolist())
    if len(tasks_to_run) < MAX_ROUTES_PER_RUN:
        for hub in HUB_ORIGINS:
            for dest in all_icaos:
                if hub != dest:
                    candidate_key = f"{hub}_{dest}_1KG"
                    if candidate_key not in existing_keys and (hub, dest, candidate_key) not in tasks_to_run:
                        tasks_to_run.append((hub, dest, candidate_key))
                        if len(tasks_to_run) >= MAX_ROUTES_PER_RUN:
                            break
            if len(tasks_to_run) >= MAX_ROUTES_PER_RUN:
                break

    # 限制單次執行數量
    tasks_to_run = tasks_to_run[:MAX_ROUTES_PER_RUN]
    print(f"🚀 本次排程預計自動抓取 {len(tasks_to_run)} 條航線截圖: {[t[2] for t in tasks_to_run]}")

    for orig, dest, r_key in tasks_to_run:
        print(f"⏳ 正在連線 ICAO 官網擷取: {orig} -> {dest} ({r_key})...")
        res = await query_icao_and_screenshot(orig, dest, 1.0, r_key)
        
        # 更新或新增至 cache_db.csv
        if r_key in cache_df['route_key'].values:
            cache_df.loc[cache_df['route_key'] == r_key, ['distance_km', 'fuel_burn_kg', 'co2_per_kg', 'screenshot_file', 'status']] = [
                res['distance_km'], res['fuel_burn_kg'], res['co2_per_kg'], res['screenshot_file'], res['status']
            ]
        else:
            new_row = pd.DataFrame([res])
            # 對齊欄位
            for col in cache_df.columns:
                if col not in new_row.columns:
                    new_row[col] = ""
            new_row = new_row[cache_df.columns]
            cache_df = pd.concat([cache_df, new_row], ignore_index=True)

        # 每抓完一條就即時存檔
        cache_df.to_csv("cache_db.csv", index=False)
        print(f"✅ {r_key} 處理完成，狀態: {res['status']}")

if __name__ == "__main__":
    asyncio.run(main())
