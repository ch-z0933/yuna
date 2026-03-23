import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials

# --- 1. Google Sheets 連線 (維持原樣) ---
def init_connection():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open("YUNA_Sales_Data").worksheet("YUNA")

try:
    sheet = init_connection()
except Exception as e:
    st.error(f"雲端連線失敗: {e}")
    sheet = None

# --- 2. 設定區 ---
st.set_page_config(page_title="YUNA 監控戰情室", layout="wide")
st.title("🔥 ITZY Yuna 台北簽售 - 實時銷售戰情室")

API_URL = "https://www.tdkculture.com/api/merchants/6981d83a102f1c007dd4ab54/products/69b110610ce76535f6ef2b51/check_stock?variation_id=69c0abbd51d28b0016bb4cf6"

# --- 3. 初始化資料 ---
# 欄位改為：時間、單筆數量、剩餘庫存
if 'history' not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=['時間', '單筆數量', '剩餘庫存'])
if 'last_stock' not in st.session_state:
    st.session_state.last_stock = 0

# 從雲端恢復數據 (確保欄位對應正確)
if 'cloud_synced' not in st.session_state:
    if sheet:
        try:
            records = sheet.get_all_records()
            if records:
                df = pd.DataFrame(records)
                # 確保載入時只取我們需要的欄位
                st.session_state.history = df[['時間', '單筆數量', '剩餘庫存']].iloc[::-1]
                st.session_state.last_stock = int(df.iloc[-1]['剩餘庫存'])
            st.session_state.cloud_synced = True
        except:
            pass

def get_data():
    headers = {"User-Agent": "Mozilla/5.0 ..."} # 建議保留 header
    try:
        res = requests.get(f"{API_URL}&t={int(time.time())}", timeout=10)
        data = res.json()
        return data.get('left_items_quantity', 0)
    except:
        return None

# --- 4. 主程式邏輯 ---
status_placeholder = st.empty()
current_stock = get_data()

if current_stock is not None:
    tz = pytz.timezone('Asia/Taipei')
    now = datetime.now(tz).strftime("%H:%M:%S")

    # 1. 初始化基準點
    if st.session_state.last_stock == 0:
        st.session_state.last_stock = current_stock

    # 2. 核心過濾邏輯
    if current_stock < st.session_state.last_stock:
        
        # --- [最強保險] 直接檢查整個歷史紀錄中的「剩餘庫存」列 ---
        # 只要這個數字以前出現過，就絕對不存
        already_exists = False
        if not st.session_state.history.empty:
            if current_stock in st.session_state.history['剩餘庫存'].values:
                already_exists = True
        
        if not already_exists:
            diff = st.session_state.last_stock - current_stock
            
            # 寫入雲端
            if sheet:
                try:
                    # 在寫入前最後一刻再檢查一次雲端最後一列（防止多視窗併發）
                    # 這一行雖然會慢一點點，但能極大程度防止重複
                    last_row_val = sheet.col_values(3)[-1] # 假設第 3 欄是剩餘庫存
                    if str(current_stock) != str(last_row_val):
                        sheet.append_row([now, diff, current_stock])
                        
                        # 更新本地紀錄
                        new_row = pd.DataFrame([{'時間': now, '單筆數量': diff, '剩餘庫存': current_stock}])
                        st.session_state.history = pd.concat([new_row, st.session_state.history], ignore_index=True)
                except:
                    # 如果是第一次運行或抓取失敗，依然嘗試更新本地
                    new_row = pd.DataFrame([{'時間': now, '單筆數量': diff, '剩餘庫存': current_stock}])
                    st.session_state.history = pd.concat([new_row, st.session_state.history], ignore_index=True)
            
            # 成功與否都更新基準點
            st.session_state.last_stock = current_stock
        else:
            # 發現重複庫存，僅更新基準點
            st.session_state.last_stock = current_stock

    elif current_stock > st.session_state.last_stock:
        st.session_state.last_stock = current_stock

    # --- 5. 畫面渲染 ---
    with status_placeholder.container():
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.subheader("📜 銷售變動紀錄 (最新在前)")
            st.dataframe(st.session_state.history, use_container_width=True, hide_index=True)

        with c2:
            st.subheader("🏆 排名 (單筆購買量)")
            if not st.session_state.history.empty:
                # 排名邏輯：從歷史紀錄中抓出「單筆數量」，由大到小排序
                ranking_df = st.session_state.history[['時間', '單筆數量']].copy()
                ranking_df = ranking_df.sort_values(by='單筆數量', ascending=False).reset_index(drop=True)
                ranking_df.index = ranking_df.index + 1 # 讓 index 從 1 開始變成排名
                ranking_df.index.name = "排名"
                
                # 重新命名欄位為：排名、本數、時間
                ranking_df = ranking_df.rename(columns={'單筆數量': '本數'})
                st.dataframe(ranking_df.head(100)) # 顯示前 10 名
            else:
                st.write("尚無銷售數據")

# 15 秒刷新
time.sleep(20)
st.rerun()
