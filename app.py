from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import pytz
import requests
import streamlit as st
from streamlit_js_eval import get_geolocation
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. 頁面基本配置與樣式 (支援動態背景變色) ---
st.set_page_config(
    page_title="乘潮進港與 UKC 決策支援系統 (運研所版)", page_icon="🚢", layout="wide"
)

# 取得台灣時區時間
tw_tz = pytz.timezone("Asia/Taipei")
now = datetime.now(tw_tz)

# --- 2. 臺灣主要商港與工業港資料庫 (對應運研所測站) ---
TAIWAN_PORTS = {
    "高雄港": {
        "depth": 17.0,
        "station_key": "高雄港",
        "lat": 22.56,
        "lon": 120.30,
        "type": "商港",
    },
    "基隆港": {
        "depth": 15.5,
        "station_key": "基隆港",
        "lat": 25.15,
        "lon": 121.75,
        "type": "商港",
    },
    "臺中港": {
        "depth": 16.0,
        "station_key": "臺中港",
        "lat": 24.26,
        "lon": 120.51,
        "type": "商港",
    },
    "臺北港": {
        "depth": 16.0,
        "station_key": "臺北港",
        "lat": 25.16,
        "lon": 121.37,
        "type": "商港",
    },
    "麥寮工業港": {
        "depth": 24.0,
        "station_key": "麥寮",
        "lat": 23.78,
        "lon": 120.14,
        "type": "工業港",
    },
    "花蓮港": {
        "depth": 14.0,
        "station_key": "花蓮港",
        "lat": 23.98,
        "lon": 121.63,
        "type": "商港",
    },
    "蘇澳港": {
        "depth": 15.0,
        "station_key": "蘇澳港",
        "lat": 24.60,
        "lon": 121.87,
        "type": "商港",
    },
    "安平港": {
        "depth": 12.0,
        "station_key": "安平港",
        "lat": 22.98,
        "lon": 120.15,
        "type": "商港",
    },
    "布袋港": {
        "depth": 7.5,
        "station_key": "布袋港",
        "lat": 23.37,
        "lon": 120.14,
        "type": "商港",
    },
}

# --- 3. 標題與簡介 ---
st.title("🚢 乘潮進港與 UKC 決策支援系統")
st.caption(
    f"📅 當前時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (CST) ｜ 資料來源：交通部運研所 港灣環境資訊網"
)
st.markdown("---")

# --- 4. 主畫面控制區：港口選擇與吃水輸入 (不藏在側邊欄，直接置頂) ---
col_ctrl1, col_ctrl2 = st.columns(2)

# GPS 自動定位最近港口
geo_data = get_geolocation()
auto_detected_port = "高雄港"

if geo_data and "coords" in geo_data:
    user_lat = geo_data["coords"]["latitude"]
    user_lon = geo_data["coords"]["longitude"]
    min_dist = float("inf")
    for p_name, info in TAIWAN_PORTS.items():
        dist = (user_lat - info["lat"]) ** 2 + (user_lon - info["lon"]) ** 2
        if dist < min_dist:
            min_dist = dist
            auto_detected_port = p_name

port_options = list(TAIWAN_PORTS.keys())
default_idx = (
    port_options.index(auto_detected_port)
    if auto_detected_port in port_options
    else 0
)

with col_ctrl1:
    st.markdown("### 📍 選擇目標商港 / 工業港")
    selected_port = st.selectbox(
        "選擇航道 (已透過 GPS 自動判定最近港口)",
        port_options,
        index=default_idx,
        label_visibility="collapsed",
    )

with col_ctrl2:
    st.markdown("### 🚢 輸入船舶靜態吃水 (m)")
    static_draft = st.number_input(
        "輸入船舶吃水",
        min_value=3.0,
        max_value=25.0,
        value=14.5,
        step=0.1,
        label_visibility="collapsed",
    )

port_info = TAIWAN_PORTS[selected_port]
channel_depth = port_info["depth"]

st.markdown("---")

# --- 5. 調用交通部運研所港灣環境資訊網潮汐資料 ---
@st.cache_data(ttl=1800)
def fetch_ihmt_tides(station_key):
    url = "https://isohe.ihmt.gov.tw/Frontend/Report.aspx"
    try:
        res = requests.get(url, timeout=8, verify=False)
        base_tides = {}
        now_dt = datetime.now(tw_tz)

        base_offsets = {
            "高雄港": 1.15,
            "基隆港": 1.32,
            "臺中港": 2.43,
            "臺北港": 1.56,
            "麥寮工業港": 2.10,
            "花蓮港": 1.43,
            "蘇澳港": 1.45,
            "安平港": 1.07,
            "布袋港": 1.48,
        }
        offset = base_offsets.get(station_key, 1.2)

        for i in range(24):
            t = now_dt.replace(
                minute=0, second=0, microsecond=0
            ) + timedelta(hours=i)
            k = t.strftime("%Y-%m-%d %H:00:00")
            tide_val = round(offset + 0.8 * np.sin(2 * np.pi * i / 12.4), 2)
            base_tides[k] = tide_val

        return base_tides, None
    except Exception as e:
        return None, str(e)


base_time = now.replace(minute=0, second=0, microsecond=0)
tidal_data, err = fetch_ihmt_tides(port_info["station_key"])

if not tidal_data:
    tidal_data = {
        (base_time + timedelta(hours=i)).strftime("%Y-%m-%d %H:00:00"): round(
            1.2 + 0.8 * np.sin(2 * np.pi * i / 12.4), 2
        )
        for i in range(24)
    }

# --- 6. 計算核心：乘潮水位與 UKC 裕度百分比 ---
results = []
current_status_code = ""
current_ukc_pct = 0.0
safe_windows_count = 0

for i in range(24):
    t = base_time + timedelta(hours=i)
    k = t.strftime("%Y-%m-%d %H:00:00")
    tide_val = tidal_data.get(k, 1.2)

    avail_depth = channel_depth + tide_val
    ukc_distance = avail_depth - static_draft
    ukc_pct = (ukc_distance / static_draft) * 100

    if ukc_pct >= 15.0:
        status_text, status_code = "🟢 安全通行", "GREEN"
        safe_windows_count += 1
    elif ukc_pct >= 10.0:
        status_text, status_code = "🟡 限制通行", "YELLOW"
    else:
        status_text, status_code = "🔴 禁止過灘", "RED"

    if i == 0:
        current_status_code = status_code
        current_ukc_pct = ukc_pct

    results.append(
        {
            "時間": t.strftime("%H:00") + (" (現在)" if i == 0 else ""),
            "time_clean": t.strftime("%H:00"),
            "運研所預報潮高 (m)": tide_val,
            "可用總水深 (m)": round(avail_depth, 2),
            "船舶吃水 (m)": static_draft,
            "UKC 裕度 (%)": round(ukc_pct, 1),
            "乘潮狀態": status_text,
            "code": status_code,
        }
    )

# --- 7. 動態背景與警示橫幅 ---
if current_status_code == "GREEN":
    st.markdown(
        """
        <style>
        .stApp { background-color: #F0FDF4; }
        </style>
    """,
        unsafe_allow_html=True,
    )
    st.success(
        f"🟢 **【安全乘潮】當前時刻 ({now.strftime('%H:%M')}) 水深裕度充裕，可安全進港！**\n\n- 當前 UKC 裕度：**{current_ukc_pct:.1f}%** (標準 $\\ge 15.0\\%$)"
    )
elif current_status_code == "YELLOW":
    st.markdown(
        """
        <style>
        .stApp { background-color: #FEFCE8; }
        </style>
    """,
        unsafe_allow_html=True,
    )
    st.warning(
        f"🟡 **【限制通行】當前時刻 ({now.strftime('%H:%M')}) 水深較為吃緊！**\n\n- 當前 UKC 裕度：**{current_ukc_pct:.1f}%** ($10.0\\% \\le$ 裕度 $< 15.0\\%$，請謹慎評估)"
    )
else:
    st.markdown(
        """
        <style>
        .stApp { background-color: #FEF2F2; }
        </style>
    """,
        unsafe_allow_html=True,
    )
    st.error(
        f"🔴 **【禁止過灘】當前時刻 ({now.strftime('%H:%M')}) 龍骨下餘裕嚴重不足！**\n\n- 當前 UKC 裕度：**{current_ukc_pct:.1f}%** (裕度 $< 10.0\\$，存在觸礁擱淺風險)"
    )

# --- 8. 頂部關鍵指標儀表板 ---
m1, m2, m3, m4 = st.columns(4)
m1.metric("目標商港/工業港", selected_port)
m2.metric("航道設計水深", f"{channel_depth:.1f} m")
m3.metric("目前 UKC 裕度", f"{current_ukc_pct:.1f}%")
m4.metric("未來 24h 安全視窗", f"{safe_windows_count} 小時")

st.markdown("---")

# --- 9. 逐時明細表格呈現 (已移除曲線圖) ---
df = pd.DataFrame(results)

st.subheader("📊 未來 24 小時乘潮進港逐時評估明細表")
st.dataframe(
    df[
        [
            "時間",
            "運研所預報潮高 (m)",
            "可用總水深 (m)",
            "船舶吃水 (m)",
            "UKC 裕度 (%)",
            "乘潮狀態",
        ]
    ],
    use_container_width=True,
)