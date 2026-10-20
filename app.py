import os
import re
import io
import zipfile
import asyncio
import pandas as pd
import streamlit as st
from scraper import query_icao_and_screenshot

st.set_page_config(page_title="ICAO 航空碳排與距離智慧助理", layout="wide")
st.title("✈️ ICAO 航空碳排計算與官方截圖智慧系統")
st.markdown("---")

@st.cache_data(ttl=30)
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

# 建立機場下拉選單選項 (結合中文名稱與代碼，支援模糊搜尋)
airport_options = [f"{row['airport_name']} ({row['icao']})" for _, row in dict_df.drop_duplicates(subset=['icao']).iterrows()]

# 側邊欄狀態
with st.sidebar:
    st.header("📊 雲端快取庫狀態")
    completed_count = len(cache_df[cache_df['status'] == 'Completed'])
    st.metric("已就緒標準航線", f"{completed_count} 條 (秒速命中)")
    st.info("💡 系統已啟用快取記憶體與自動轉譯機制，所有常用商務與貨運航線皆可 0 秒出圖。")

# ==================== 建立人性化雙模式 Tabs ====================
tab_batch, tab_single = st.tabs(["📦 步驟 1-A：批次 ERP 檔案上傳與預覽", "🔍 步驟 1-B：單筆快速查詢與截圖"])

# ----------------- 模式 A：批次 ERP 上傳 -----------------
with tab_batch:
    st.subheader("步驟 1：拖曳上傳 ERP 空運明細")
    uploaded_file = st.file_uploader("支援 ERP 原始格式 Excel (.xlsx) 或 CSV，免修改表頭", type=["xlsx", "xls", "csv"])

    if uploaded_file:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file, header=0)
            if "Unnamed: 0" in df.columns:
                uploaded_file.seek(0)
                df = pd.read_excel(uploaded_file, header=1)

        st.success(f"✅ 成功讀取 {len(df)} 筆資料！系統已自動識別欄位。")

        # 步驟 2：欄位對應確認
        st.markdown("### 步驟 2：欄位對應確認")
        cols = df.columns.tolist()
        c1, c2, c3 = st.columns(3)
        orig_col = c1.selectbox("出發地欄位", cols, index=cols.index("運輸起點") if "運輸起點" in cols else 0)
        dest_col = c2.selectbox("目的地欄位", cols, index=cols.index("運輸終點") if "運輸終點" in cols else 1)
        weight_col = c3.selectbox("出貨總重(公噸)欄位", cols, index=next((i for i, c in enumerate(cols) if "出貨總量" in c or "重量" in c), 0))

        df['起點_ICAO'] = df[orig_col].apply(lambda x: translate_to_icao(x, dict_df))
        df['終點_ICAO'] = df[dest_col].apply(lambda x: translate_to_icao(x, dict_df))
        df['route_key'] = df['起點_ICAO'] + "_" + df['終點_ICAO'] + "_1KG"

        unique_routes = df[['起點_ICAO', '終點_ICAO', 'route_key']].drop_duplicates()
        st.info(f"📊 分析摘要：共 **{len(df)}** 筆出貨紀錄，自動歸納出 **{len(unique_routes)}** 條獨特航線。")

        # 步驟 3：執行計算與線上預覽
        st.markdown("### 步驟 3：計算與線上成果預覽")
        if st.button("🚀 開始計算碳排、延噸公里並產生官方佐證圖檔", type="primary"):
            cache_map = cache_df.set_index('route_key').to_dict(orient='index')
            
            missing_routes = [r for r in unique_routes.to_dict(orient='records') 
                              if r['route_key'] not in cache_map or cache_map[r['route_key']]['status'] != 'Completed']
            
            if missing_routes:
                prog = st.progress(0)
                for idx, r in enumerate(missing_routes):
                    res = asyncio.run(query_icao_and_screenshot(r['起點_ICAO'], r['dest_icao'], 1.0, r['route_key']))
                    cache_map[r['route_key']] = res
                    prog.progress((idx + 1) / len(missing_routes))

            df['ICAO_航程距離(KM)'] = df['route_key'].map(lambda k: cache_map.get(k, {}).get('distance_km', 0))
            df['ICAO_飛機總耗油(KG)'] = df['route_key'].map(lambda k: cache_map.get(k, {}).get('fuel_burn_kg', 0))
            df['ICAO_1KG單位碳排(KG)'] = df['route_key'].map(lambda k: cache_map.get(k, {}).get('co2_per_kg', 0))
            
            weight_tons = pd.to_numeric(df[weight_col], errors='coerce').fillna(0)
            df['計算_延噸公里(tkm)'] = (weight_tons * df['ICAO_航程距離(KM)']).round(4)
            df['計算_ICAO總碳排(KG_CO2)'] = (weight_tons * 1000 * df['ICAO_1KG單位碳排(KG)']).round(4)
            df['佐證截圖檔名'] = df['route_key'] + ".png"

            st.success("🎉 計算完成！以下為前 20 筆預覽結果：")
            st.dataframe(df[[orig_col, '起點_ICAO', dest_col, '終點_ICAO', weight_col, 
                             'ICAO_航程距離(KM)', '計算_延噸公里(tkm)', 'ICAO_1KG單位碳排(KG)', '計算_ICAO總碳排(KG_CO2)']].head(20), use_container_width=True)

            # 步驟 4：一鍵打包下載
            st.markdown("### 步驟 4：一鍵下載完整成果包")
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
                label="📥 下載完整成果包 (.ZIP 含 Excel 總表與官方截圖資料夾)",
                data=zip_buffer.getvalue(),
                file_name="ICAO_AirCargo_Carbon_Report.zip",
                mime="application/zip",
                type="primary"
            )

            # 額外提供：單張截圖線上預覽選單
            st.markdown("#### 🖼️ 線上憑證截圖即時預覽")
            selected_route_preview = st.selectbox("選擇要檢視官方憑證截圖的航線", df['route_key'].unique())
            preview_img = f"screenshots/{selected_route_preview}.png"
            if os.path.exists(preview_img):
                st.image(preview_img, caption=f"ICAO 官方 Summary 憑證截圖: {selected_route_preview}", use_column_width=True)


# ----------------- 模式 B：單筆快速查詢 -----------------
with tab_single:
    st.subheader("🔍 單筆航線即時查詢與憑證截圖產出")
    st.markdown("適合臨時查詢特定航段或主管交辦之抽查案件，輸入起訖與重量即可馬上看圖！")

    col_s1, col_s2, col_s3 = st.columns(3)
    origin_sel = col_s1.selectbox("選擇出發機場", airport_options, index=2) # 預設桃園 RCTP
    dest_sel = col_s2.selectbox("選擇到達機場", airport_options, index=7)   # 預設吉隆坡 WMKK
    weight_input = col_s3.number_input("輸入貨物重量 (KG)", min_value=1.0, value=1.0, step=1.0)

    # 提取代碼
    orig_code = re.search(r'\(([A-Z]{4})\0?\)', origin_sel).group(1) if re.search(r'\(([A-Z]{4})\0?\)', origin_sel) else "RCTP"
    # 修正正則
    orig_code = origin_sel.split('(')[-1].strip(')')
    dest_code = dest_sel.split('(')[-1].strip(')')

    if st.button("🔎 立即查詢並顯示官方憑證截圖", type="primary"):
        with st.spinner("正在計算並產生官方規格憑證..."):
            res = asyncio.run(query_icao_and_screenshot(orig_code, dest_code, weight_input))
            
        st.success("✨ 查詢成功！")
        
        # 秀出數據指標
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("總航程距離", f"{res['distance_km']:,.0f} KM")
        m2.metric("飛機總耗油量", f"{res['fuel_burn_kg']:,.0f} KG")
        m3.metric("單位碳排 (1KG)", f"{res['co2_per_kg']:.2f} KG")
        m4.metric(f"總貨重 ({weight_input}KG) 碳排", f"{(res['co2_per_kg']):.2f} KG")

        # 直接在網頁上展示截圖
        st.markdown("### 📄 ICAO 官方 Summary 憑證畫面預覽[cite: 1]")
        if os.path.exists(res['screenshot_file']):
            st.image(res['screenshot_file'], caption=f"官方佐證截圖: {orig_code} -> {dest_code} ({weight_input}KG)", use_column_width=True)
            
            with open(res['screenshot_file'], "rb") as file:
                st.download_button(
                    label="📥 下載此張官方憑證截圖 (.png)",
                    data=file,
                    file_name=f"{orig_code}_{dest_code}_{int(weight_input)}KG.png",
                    mime="image/png"
                )
