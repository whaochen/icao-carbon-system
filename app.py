import os
import re
import io
import zipfile
import pandas as pd
import streamlit as st
from scraper import calc_icao_methodology, query_icao_and_screenshot

st.set_page_config(page_title="ICAO 航空碳排與距離智慧助理", layout="wide")
st.title("✈️ ICAO 航空碳排計算與官方截圖智慧系統")
st.markdown("---")

@st.cache_data(ttl=5)
def load_databases():
    dict_df = pd.read_csv("airports_dict.csv")
    cache_df = pd.read_csv("cache_db.csv")
    return dict_df, cache_df

dict_df, cache_df = load_databases()

# 智慧模糊代碼轉譯
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

# 建立機場下拉選單選項 (支援模糊查詢與名稱對照)
airport_options = [f"{row['airport_name']} ({row['icao']})" for _, row in dict_df.drop_duplicates(subset=['icao']).iterrows()]
icao_to_name = dict(zip(dict_df['icao'], dict_df['airport_name']))

with st.sidebar:
    st.header("📊 系統狀態與背景預熱機制")
    current_count = len(cache_df)
    st.metric("在庫航線總數", f"{current_count} 條")
    
    with st.expander("⚙️ 關於背景預熱機制"):
        st.markdown("""
        * **GitHub Actions 自動化：** 專案中的 `.github/workflows/prewarm_routes.yml` 會定期觸發背景排程 (`prewarm_worker.py`)。
        * **自動補齊：** 當 ERP 匯入新航線或標記為 `Pending` 時，背景機器人會自動連線 ICAO 官網抓取最新截圖並更新 `cache_db.csv`。
        """)

    display_cols = [c for c in ['route_key', 'distance_km', 'co2_per_kg', 'status'] if c in cache_df.columns]
    st.dataframe(cache_df[display_cols], hide_index=True)

tab_single, tab_batch = st.tabs(["🔍 模式 1：單筆模糊查詢與動態新增", "📦 模式 2：批次 ERP 檔案上傳與打包下載"])

# ==================== 模式 1：單筆模糊查詢與動態新增 ====================
with tab_single:
    st.subheader("🔍 單筆航線模糊查詢與動態新增")
    st.markdown("支援輸入中文名稱或機場代碼進行模糊查詢。若資料庫中尚無該航線，系統將自動為您新增並產出截圖！")

    col_s1, col_s2, col_s3 = st.columns(3)
    origin_sel = col_s1.selectbox("選擇出發機場 (支援關鍵字)", airport_options, index=0)
    dest_sel = col_s2.selectbox("選擇到達機場 (支援關鍵字)", airport_options, index=7)
    weight_input = col_s3.number_input("試算出貨重量 (KG)", min_value=1.0, value=1.0, step=10.0)

    orig_code = origin_sel.split('(')[-1].strip(')')
    dest_code = dest_sel.split('(')[-1].strip(')')
    route_key = f"{orig_code}_{dest_code}_1KG"

    # 檢查快取資料庫中是否有此航線
    cache_map = cache_df.set_index('route_key').to_dict(orient='index')

    if route_key in cache_map and cache_map[route_key].get('status') == 'Completed':
        row = cache_map[route_key]
        dist_km = float(row['distance_km'])
        fuel_kg = float(row['fuel_burn_kg'])
        co2_1kg = float(row['co2_per_kg'])
        img_path = f"screenshots/{route_key}.png"

        st.success("✨ 已從快取庫秒速命中該航線紀錄！")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("總航程距離", f"{dist_km:,.0f} KM")
        m2.metric("飛機總耗油量", f"{fuel_kg:,.0f} KG")
        m3.metric("單位碳排 (1 KG)", f"{co2_1kg:.2f} KG")
        m4.metric(f"試算總碳排 ({weight_input:g} KG)", f"{(co2_1kg * weight_input):,.2f} KG")

        st.markdown(f"#### 🖼️ 官方佐證截圖預覽 (`{img_path}`)")
        if os.path.exists(img_path):
            st.image(img_path, caption=f"官方截圖：{route_key}.png", use_container_width=True)
            with open(img_path, "rb") as file:
                st.download_button("📥 下載此張官方憑證截圖 (.png)", data=file, file_name=f"{route_key}.png", mime="image/png", type="primary")
        else:
            st.warning("⚠️ 找不到對應的截圖檔案。")
    else:
        st.warning(f"⚠️ 目前快取庫中尚無 **{orig_code} ➔ {dest_code}** 的建檔紀錄。")
        if st.button("✨ 立即新增此航線並產出官方憑證截圖", type="primary"):
            with st.spinner("正在計算並建立新航線紀錄與憑證..."):
                # 計算並新增
                res = asyncio.run(query_icao_and_screenshot(orig_code, dest_code, 1.0, route_key))
                
                # 更新 cache_db.csv
                new_row = pd.DataFrame([{
                    "route_key": route_key,
                    "origin_icao": orig_code,
                    "dest_icao": dest_code,
                    "distance_km": res['distance_km'],
                    "fuel_burn_kg": res['fuel_burn_kg'],
                    "co2_per_kg": res['co2_per_kg'],
                    "status": "Completed"
                }])
                updated_cache = pd.concat([cache_df[cache_df['route_key'] != route_key], new_row], ignore_index=True)
                updated_cache.to_csv("cache_db.csv", index=False)
                st.cache_data.clear()
            st.success("🎉 新航線已成功新增並存入資料庫！請重新整理頁面檢視成果。")
            st.rerun()

# ==================== 模式 2：批次 ERP 上傳 ====================
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
            label="📥 一鍵下載完整成果包 (.ZIP 含計算總表與官方截圖)",
            data=zip_buffer.getvalue(),
            file_name="ICAO_AirCargo_Carbon_Report.zip",
            mime="application/zip",
            type="primary"
        )
