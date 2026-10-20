import os
import re
import io
import zipfile
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ICAO 航空碳排與距離智慧助理", layout="wide")
st.title("✈️ ICAO 航空碳排計算與官方截圖智慧系統")
st.markdown("---")

@st.cache_data(ttl=10)
def load_databases():
    dict_df = pd.read_csv("airports_dict.csv")
    cache_df = pd.read_csv("cache_db.csv")
    return dict_df, cache_df

dict_df, cache_df = load_databases()

# 機場名稱字典映射 (用來顯示中文名稱)
icao_to_name = dict(zip(dict_df['icao'], dict_df['airport_name']))

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

with st.sidebar:
    st.header("📊 已就緒航線快取庫 (16條)")
    st.metric("在庫航線數", f"{len(cache_df)} 條")
    st.dataframe(cache_df[['route_key', 'distance_km', 'co2_per_kg', 'note']], hide_index=True)

tab_single, tab_batch = st.tabs(["🔍 模式 1：從已就緒 16 條航線快速查詢與預覽截圖", "📦 模式 2：批次 ERP 檔案上傳與打包下載"])

# ==================== 模式 1：直接從 16 條已就緒航線拿出截圖 ====================
with tab_single:
    st.subheader("🔍 直接檢視已就緒之 16 條航線數據與官方截圖")
    
    # 建立好讀的下拉選單：例如 "RCTP -> VTBS | 台灣桃園->泰國曼谷(22筆)"
    route_options = {}
    for _, row in cache_df.iterrows():
        r_key = row['route_key']
        orig, dest = row['origin_icao'], row['dest_icao']
        note = row.get('note', '')
        label = f"{orig} ➔ {dest} ｜ {note} (1KG 碳排: {row['co2_per_kg']} KG / 距離: {row['distance_km']} KM)"
        route_options[label] = row

    c1, c2 = st.columns([3, 1])
    selected_label = c1.selectbox("📂 請選擇要調閱的航線（共 16 條已建檔航線）：", list(route_options.keys()))
    weight_input = c2.number_input("試算出貨重量 (KG)", min_value=1.0, value=1.0, step=10.0)

    selected_row = route_options[selected_label]
    r_key = selected_row['route_key']
    orig_code = selected_row['origin_icao']
    dest_code = selected_row['dest_icao']
    dist_km = float(selected_row['distance_km'])
    fuel_kg = float(selected_row['fuel_burn_kg'])
    co2_1kg = float(selected_row['co2_per_kg'])
    img_path = f"screenshots/{r_key}.png"

    st.markdown("#### 📊 航線計算結果")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("總航程距離", f"{dist_km:,.0f} KM")
    m2.metric("飛機總耗油量", f"{fuel_kg:,.0f} KG")
    m3.metric("單位碳排 (1 KG)", f"{co2_1kg:.2f} KG")
    m4.metric(f"試算總碳排 ({weight_input:g} KG)", f"{(co2_1kg * weight_input):,.2f} KG")

    st.markdown("#### 🖼️ 倉庫內對應之佐證截圖 (`" + img_path + "`)")
    if os.path.exists(img_path):
        st.image(img_path, caption=f"佐證截圖檔名：{r_key}.png", use_container_width=True)
        with open(img_path, "rb") as file:
            st.download_button(
                label=f"📥 單獨下載此張截圖 ({r_key}.png)",
                data=file,
                file_name=f"{r_key}.png",
                mime="image/png",
                type="primary"
            )
    else:
        st.warning(f"⚠️ 找不到 `{img_path}` 檔案，請確認該圖檔已上傳至 GitHub 的 `screenshots/` 資料夾中。")

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
