import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials

# --- 1. Google Sheets 核心連線 ---
def init_connection():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    # 請確保你的 Google Sheet 名字是 YUNA_Sales_Data
    return client.open("YUNA_Sales_Data").worksheet("YUNA")

try:
    sheet = init_connection()
except Exception as e:
    st.error(f"雲端連線失敗: {e}")
    sheet = None

# --- 2. 原始設定區 (更新為 TDK API) ---
st.set_page_config(page_title="YUNA 簽售監控", layout="wide")
st.title("🔥 ITZY Yuna 台北簽售 - 實時銷售監控")

# 這是你提供的 TDK 庫存檢查 API
API_URL = "https://www.tdkculture.com/api/merchants/6981d83a102f1c007dd4ab54/products/69b110610ce76535f6ef2b51/check_stock?variation_id=69c0abbd51d28b0016bb4cf6"
INITIAL_STOCK = 8000  # 假設初始庫存是 8000

# --- 3. 初始化資料 ---
if 'history' not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=['時間', '剩餘庫存', '本次銷量', '總累計銷量'])
if 'last_stock' not in st.session_state:
    st.session_state.last_stock = 0

# 啟動時從雲端恢復最後一筆數據
if 'cloud_synced' not in st.session_state:
    if sheet:
        try:
            records = sheet.get_all_records()
            if records:
                df = pd.DataFrame(records)
                st.session_state.history = df.iloc[::-1] # 反轉顯示最新在上面
                st.session_state.last_stock = int(df.iloc[-1]['剩餘庫存'])
            st.session_state.cloud_synced = True
        except:
            pass

def get_data():
    # 模擬成真實瀏覽器訪問，不然 TDK 會回傳 403 錯誤
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        # 在網址後面加上隨機時間戳防止快取
        res = requests.get(f"{API_URL}&t={int(time.time())}", headers=headers, timeout=10)
        
        # 如果狀態碼不是 200，在畫面上顯示
        if res.status_code != 200:
            st.error(f"API 回傳錯誤代碼: {res.status_code}")
            return None
            
        data = res.json()
        stock = data.get('left_items_quantity', 0)
        return stock
    except Exception as e:
        st.error(f"連線出錯: {e}")
        return None

# --- 4. 主程式執行 ---
status_placeholder = st.empty()

current_stock = get_data()

if current_stock is not None:
    tz = pytz.timezone('Asia/Taipei')
    now = datetime.now(tz).strftime("%H:%M:%S")

    # 如果是第一次運行，設定初始基準
    if st.session_state.last_stock == 0:
        st.session_state.last_stock = current_stock

    # 檢查是否有變動 (庫存減少代表賣出)
    if current_stock != st.session_state.last_stock:
        diff = st.session_state.last_stock - current_stock
        total_sold = INITIAL_STOCK - current_stock
        
        # 寫入 Google Sheets
        if sheet:
            try:
                # 欄位：時間, 剩餘庫存, 本次銷量, 總累計銷量
                sheet.append_row([now, current_stock, diff, total_sold])
            except Exception as e:
                st.warning(f"寫入雲端失敗: {e}")

        # 更新本地 session_state
        new_row = pd.DataFrame([{'時間': now, '剩餘庫存': current_stock, '本次銷量': diff, '總累計銷量': total_sold}])
        st.session_state.history = pd.concat([new_row, st.session_state.history], ignore_index=True)
        st.session_state.last_stock = current_stock

    # --- 畫面渲染 ---
    with status_placeholder.container():
        col1, col2, col3 = st.columns(3)
        col1.metric("📦 目前剩餘庫存", f"{current_stock} 本")
        
        # 計算總銷量 (假設從 8000 開始扣)
        cumulative_sold = INITIAL_STOCK - current_stock
        col2.metric("📈 累計已售出", f"{cumulative_sold} 本", delta=None)
        
        col3.write(f"⏱️ 最後更新時間: {now}")

        st.write("### 📜 詳細銷售變動日誌")
        st.dataframe(st.session_state.history, use_container_width=True)

# 每 15 秒重新整理一次
time.sleep(15)
st.rerun()
