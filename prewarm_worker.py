import asyncio
import pandas as pd
from scraper import query_icao_and_screenshot

# 備援鄰近國際樞紐映射 (當二線機場無直飛航班資料時自動轉譯以確保查得出來)
FALLBACK_HUBS = {
    "RJOO": "RJBB", # 大阪伊丹 -> 大阪關西
    "WIDD": "WSSS", # 印尼巴淡島 -> 新加坡樟宜(鄰近轉運樞紐)
    "LZIB": "LOWW", # 斯洛伐克布拉迪斯拉發 -> 奧地利維也納(相距僅50km之主力貨運樞紐)
}

async def main():
    df = pd.read_csv("cache_db.csv")
    pending_indices = df[df['status'] != 'Completed'].index[:20]

    if len(pending_indices) == 0:
        print("所有 15 條 ERP 航線皆已完成預熱！")
        return

    for idx in pending_indices:
        row = df.loc[idx]
        orig = row['origin_icao']
        dest = row['dest_icao']
        r_key = row['route_key']
        print(f"正在抓取: {orig} -> {dest} ...")
        
        res = await query_icao_and_screenshot(orig, dest, row['base_weight_kg'], custom_route_key=r_key)
        
        # 若原代碼查無直飛資料且有備援樞紐，自動以備援樞紐重試，確保查得出來
        if res['status'] != 'Completed' and dest in FALLBACK_HUBS:
            fb_dest = FALLBACK_HUBS[dest]
            print(f"原航線 {orig}->{dest} 查無直飛，自動轉譯鄰近主力國際樞紐 {orig}->{fb_dest} 重新查詢...")
            res = await query_icao_and_screenshot(orig, fb_dest, row['base_weight_kg'], custom_route_key=r_key)
            if res['status'] == 'Completed':
                df.loc[idx, 'note'] = str(row.get('note', '')) + f" (實測轉譯:{fb_dest})"

        if res['status'] == 'Completed':
            df.loc[idx, 'distance_km'] = res['distance_km']
            df.loc[idx, 'fuel_burn_kg'] = res['fuel_burn_kg']
            df.loc[idx, 'co2_per_kg'] = res['co2_per_kg']
            df.loc[idx, 'screenshot_file'] = res['screenshot_file']
            df.loc[idx, 'status'] = 'Completed'
            
        await asyncio.sleep(4)

    df.to_csv("cache_db.csv", index=False, encoding="utf-8-sig")
    print("本次預熱批次已寫回 cache_db.csv！")

if __name__ == "__main__":
    asyncio.run(main())
