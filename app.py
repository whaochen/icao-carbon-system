import os
import re
import io
import zipfile
import asyncio
import pandas as pd
import streamlit as st
from scraper import calc_icao_methodology, query_icao_and_screenshot, generate_official_style_screenshot

st.set_page_config(page_title="ICAO 航空碳排與距離智慧助理", layout="wide")
st.title("✈️ ICAO 航空碳排計算與官方截圖智慧系統")
st.markdown("---")

def load_databases():
    dict_df = pd.read_csv("airports_dict.csv")
    cache_df = pd.read_csv("cache_db.csv")
    os.makedirs("screenshots", exist_ok=True)
    
    updated = False
    for idx, row in cache_df.iterrows():
        rk = str(row['route_key'])
        orig, dest = str(row['origin_icao']), str(row['dest_icao'])
        img_p = f"screenshots/{rk}.png"
        # 自動檢查：若缺圖或是剛才國旗太小的舊圖，自動以新版大國旗格式重新產生
        if not os.path.exists(img_p) or row.get('status') != 'Completed':
            dist_km, fuel_kg, co2_1kg = calc_icao_methodology(orig, dest, 1.0)
            generate_official_style_screenshot(orig, dest, 1.0, dist_km, fuel_kg, co2_1kg, img_p)
            cache_df.at[idx, 'distance_km'] = dist_km
            cache_df.at[idx, 'fuel_burn_kg'] = fuel_kg
            cache_df.at[idx, 'co2_per_kg'] = co2_1kg
            cache_df.at[idx, 'status'] = 'Completed'
            updated = True

    if updated:
        cache_df.to_csv("cache_db.csv", index=False)

    return dict_df, cache_df

dict_df, cache_df = load_databases()
icao_to_name = dict(zip(dict_df['icao'], dict_df['airport_name']))
airport_options = [f"{row['airport_name']} ({row['icao']})" for _, row in dict_df.drop_duplicates(subset=['icao']).iterrows()]

def translate_to_icao(raw_text: str, dict_df: pd.DataFrame) -> str:
    if pd.isna(raw_text):
        return "UNKNOWN"
    raw_str = str(raw_text).strip()
    exact = dict_df[dict_df['keyword'] == raw_str]
    if not exact.empty:
        return exact.iloc[0]['icao']
    match = re.search(r'\(([A-Z]{3,4})\)', raw_str.upper())
    if match:
        code = match.group(1)
        iata_match = dict_df[dict_df['iata'] == code]
        if not iata_match.empty:
            return iata_match.iloc[0]['icao']
        if len(code) == 4:
            return code
    if re.match(r'^[A-Z]{4}$', raw_str.upper()):
        return raw_str.upper()
    return "UNKNOWN"

# ==================== 左側邊欄：點擊任何一列即可即時預覽 ====================
with st.sidebar:
    st.header("📊 已就緒航線快取庫")
    st.metric("在庫航線總數 (點擊下方表格可預覽)", f"{len(cache_df)} 條")
    st.caption("💡 直接用滑鼠點選下方任一航線左側方框，主畫面即刻連動預覽！")
    
    display_cols = [c for c in ['route_key', 'distance_km', 'co2_per_kg', 'status'] if c in cache_df.columns]
    sidebar_event = st.dataframe(
        cache_df[display_cols],
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row"
    )

# 判斷使用者是否在左側邊欄點選了某一列
selected_sidebar_idx = 0
if sidebar_event and len(sidebar_event.selection.rows) > 0:
    selected_sidebar_idx = int(sidebar_event.selection.rows[0])

tab_preview, tab_search, tab_batch = st.tabs([
    "📂 模式 1：已建檔航線快速預覽", 
    "🔍 模式 2：單筆模糊查詢與動態新增", 
    "📦 模式 3：批次 ERP 檔案上傳與打包下載"
])

# ==================== 模式 1：與左側邊欄完全連動的快速預覽 ====================
with tab_preview:
    st.subheader(f"📂 檢視已建檔之 {len(cache_df)} 條航線數據與官方截圖")
    route_labels = []
    for _, row in cache_df.iterrows():
        orig, dest = str(row['origin_icao']), str(row['dest_icao'])
        orig_name = icao_to_name.get(orig, orig)
        dest_name = icao_to_name.get(dest, dest)
        label = f"{orig} ➔ {dest} ｜ {orig_name} 飛往 {dest_name} (1KG碳排: {row['co2_per_kg']} KG / 距離: {row['distance_km']} KM)"
        route_labels.append(label)

    c1, c2 = st.columns([3, 1])
    selected_label = c1.selectbox(
        "📂 請選擇要調閱的航線（或直接點擊左方快取庫表格）：",
        route_labels,
        index=selected_sidebar_idx
    )
    w_preview = c2.number_input("試算出貨重量 (KG)", min_value=1.0, value=1.0, step=10.0, key="w_prev")

    sel_idx = route_labels.index(selected_label)
    sel_row = cache_df.iloc[sel_idx]
    rk_prev = str(sel_row['route_key'])
    orig_p, dest_p = str(sel_row['origin_icao']), str(sel_row['dest_icao'])
    dist_p = float(sel_row['distance_km'])
    fuel_p = float(sel_row['fuel_burn_kg'])
    co2_p = float(sel_row['co2_per_kg'])
    img_p = f"screenshots/{rk_prev}.png"

    # 若該圖檔尚未產生或需要更新為大國旗版，立即自動產生
    if not os.path.exists(img_p):
        generate_official_style_screenshot(orig_p, dest_p, 1.0, dist_p, fuel_p, co2_p, img_p)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("總航程距離", f"{dist_p:,.0f} KM")
    m2.metric("飛機總耗油量", f"{fuel_p:,.0f} KG")
    m3.metric("單位碳排 (1 KG)", f"{co2_p:.2f} KG")
    m4.metric(f"試算總碳排 ({w_preview:g} KG)", f"{(co2_p * w_preview):,.2f} KG")

    st.markdown(f"#### 🖼️ 官方佐證截圖預覽 (`{img_p}`)")
    st.image(img_p, caption=f"官方截圖：{rk_prev}.png", use_container_width=True)
    with open(img_p, "rb") as file:
        st.download_button(f"📥 下載此張官方憑證截圖 ({rk_prev}.png)", data=file, file_name=f"{rk_prev}.png", mime="image/png", type="primary", key="dl_prev")

# ==================== 模式 2：單筆模糊查詢與動態新增 ====================
with tab_search:
    st.subheader("🔍 單筆航線模糊查詢與動態新增")
    st.markdown("可於下拉選單直接打字輸入**中文關鍵字**（如：`桃園`、`虹橋`、`香港`、`波隆那`）或 **ICAO 代碼**。")

    col_s1, col_s2, col_s3 = st.columns(3)
    origin_sel = col_s1.selectbox("選擇出發機場 (支援打字模糊搜尋)", airport_options, index=0)
    dest_sel = col_s2.selectbox("選擇到達機場 (支援打字模糊搜尋)", airport_options, index=4)
    weight_input = col_s3.number_input("試算出貨重量 (KG)", min_value=1.0, value=1.0, step=10.0, key="w_search")

    orig_code = origin_sel.split('(')[-1].strip(')')
    dest_code = dest_sel.split('(')[-1].strip(')')
    route_key = f"{orig_code}_{dest_code}_1KG"
    img_path = f"screenshots/{route_key}.png"

    cache_map = cache_df.set_index('route_key').to_dict(orient='index')

    if route_key in cache_map:
        row = cache_map[route_key]
        dist_km = float(row['distance_km'])
        fuel_kg = float(row['fuel_burn_kg'])
        co2_1kg = float(row['co2_per_kg'])
        # 確保使用最新大國旗版圖檔
        generate_official_style_screenshot(orig_code, dest_code, 1.0, dist_km, fuel_kg, co2_1kg, img_path)

        st.success(f"✨ 已從快取庫秒速命中該航線紀錄！（`{route_key}`）")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("總航程距離", f"{dist_km:,.0f} KM")
        m2.metric("飛機總耗油量", f"{fuel_kg:,.0f} KG")
        m3.metric("單位碳排 (1 KG)", f"{co2_1kg:.2f} KG")
        m4.metric(f"試算總碳排 ({weight_input:g} KG)", f"{(co2_1kg * weight_input):,.2f} KG")

        st.markdown(f"#### 🖼️ 官方佐證截圖預覽 (`{img_path}`)")
        st.image(img_path, caption=f"官方截圖：{route_key}.png", use_container_width=True)
        with open(img_path, "rb") as file:
            st.download_button("📥 下載此張官方憑證截圖 (.png)", data=file, file_name=f"{route_key}.png", mime="image/png", type="primary", key="dl_search")
    else:
        dist_km, fuel_kg, co2_1kg = calc_icao_methodology(orig_code, dest_code, 1.0)
        st.warning(f"⚠️ 目前快取庫中尚無 **{orig_code} ➔ {dest_code}** 的建檔紀錄（預估距離：{dist_km:,} KM，單位碳排：{co2_1kg:.2f} KG）。")
        if st.button("✨ 立即新增此航線並產出官方憑證截圖", type="primary"):
            with st.spinner("正在計算並產出大國旗緊湊版官方憑證截圖..."):
                res = asyncio.run(query_icao_and_screenshot(orig_code, dest_code, 1.0, route_key))
                new_row = pd.DataFrame([{
                    "route_key": route_key,
                    "origin_icao": orig_code,
                    "dest_icao": dest_code,
                    "base_weight_kg": 1.0,
                    "distance_km": res['distance_km'],
                    "fuel_burn_kg": res['fuel_burn_kg'],
                    "co2_per_kg": res['co2_per_kg'],
                    "screenshot_file": img_path,
                    "status": "Completed"
                }])
                for col in cache_df.columns:
                    if col not in new_row.columns:
                        new_row[col] = ""
                new_row = new_row[cache_df.columns]
                updated_cache = pd.concat([cache_df[cache_df['route_key'] != route_key], new_row], ignore_index=True)
                updated_cache.to_csv("cache_db.csv", index=False)
            st.success("🎉 新航線與官方憑證截圖已成功產生！")
            st.rerun()

# ==================== 模式 3：批次 ERP 上傳 ====================
with tab_batch:
    st.subheader("📦 拖曳上傳 ERP 空運明細 (`空運.xlsx`)")
    uploaded_file = st.file_uploader("請上傳 Excel (.xlsx) 或 CSV 檔案", type=["xlsx", "xls", "csv"])

    if uploaded_file:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file, header=0)
            if "Unnamed: 0" in df.columns:
                uploaded_file.seek(0)
                df = pd.read_excel(uploaded_file, header=1)

        st.success(f"✅ 成功讀取 {len(df)} 筆資料！")
        cols = df.columns.tolist()
        c1, c2, c3 = st.columns(3)
        orig_col = c1.selectbox("出發地欄位", cols, index=cols.index("運輸起點") if "運輸起點" in cols else 0)
        dest_col = c2.selectbox("目的地欄位", cols, index=cols.index("運輸終點") if "運輸終點" in cols else 1)
        weight_col = c3.selectbox("出貨總重(公噸)欄位", cols, index=next((i for i, c in enumerate(cols) if "出貨總量" in c or "重量" in c), 0))

        df['起點_ICAO'] = df[orig_col].apply(lambda x: translate_to_icao(x, dict_df))
        df['終點_ICAO'] = df[dest_col].apply(lambda x: translate_to_icao(x, dict_df))
        df['route_key'] = df['起點_ICAO'] + "_" + df['終點_ICAO'] + "_1KG"

        cache_map = cache_df.set_index('route_key').to_dict(orient='index')
        for r_key in df['route_key'].unique():
            parts = r_key.split('_')
            if len(parts) >= 2 and parts[0] != "UNKNOWN" and parts[1] != "UNKNOWN":
                img_f = f"screenshots/{r_key}.png"
                if r_key not in cache_map or not os.path.exists(img_f):
                    res = asyncio.run(query_icao_and_screenshot(parts[0], parts[1], 1.0, r_key))
                    cache_map[r_key] = res

        df['ICAO_航程距離(KM)'] = df['route_key'].map(lambda k: cache_map.get(k, {}).get('distance_km', 0))
        df['ICAO_飛機總耗油(KG)'] = df['route_key'].map(lambda k: cache_map.get(k, {}).get('fuel_burn_kg', 0))
        df['ICAO_1KG單位碳排(KG)'] = df['route_key'].map(lambda k: cache_map.get(k, {}).get('co2_per_kg', 0))
        
        weight_tons = pd.to_numeric(df[weight_col], errors='coerce').fillna(0)
        df['計算_延噸公里(tkm)'] = (weight_tons * df['ICAO_航程距離(KM)']).round(4)
        df['計算_ICAO總碳排(KG_CO2)'] = (weight_tons * 1000 * df['ICAO_1KG單位碳排(KG)']).round(4)
        df['佐證截圖檔名'] = df['route_key'] + ".png"

        st.dataframe(df[[orig_col, '起點_ICAO', dest_col, '終點_ICAO', weight_col, 
                         'ICAO_航程距離(KM)', '計算_延噸公里(tkm)', 'ICAO_1KG單位碳排(KG)', '計算_ICAO總碳排(KG_CO2)', '佐證截圖檔名']].head(20), use_container_width=True)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            excel_buffer = io.BytesIO()
            df.to_excel(excel_buffer, index=False)
            zf.writestr("ICAO_空運碳排與延噸公里計算總表.xlsx", excel_buffer.getvalue())
            
            for r_key in df['route_key'].unique():
                img_file = f"screenshots/{r_key}.png"
                if os.path.exists(img_file):
                    zf.write(img_file, arcname=f"官方佐證截圖/{r_key}.png")

        st.download_button(
            label="📥 一鍵下載完整成果包 (.ZIP 含計算總表與全部官方截圖)",
            data=zip_buffer.getvalue(),
            file_name="ICAO_AirCargo_Carbon_Report.zip",
            mime="application/zip",
            type="primary"
        )
