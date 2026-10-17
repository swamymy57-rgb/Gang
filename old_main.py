
import os
import io
import json
import sqlite3
import html
from datetime import datetime, timezone
from urllib.parse import quote_plus

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf
import feedparser
import streamlit.components.v1 as components
from PIL import Image

APP_TITLE = "AI Trading Assistant"
DB_PATH = os.getenv("TRADING_DB_PATH", "trading_memory.db")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="wide")
st.title("📈 AI Trading Assistant")
st.caption("Market News • Chart Vision • Technical Signals")
st.warning(
    "విశ్లేషణ సమాచార ప్రయోజనాల కోసమే. సంకేతాలు లాభాలకు హామీ కావు. "
    "నిజమైన డబ్బుతో ట్రేడ్ చేసే ముందు స్వతంత్రంగా పరిశీలించండి."
)

# ---------------- DATABASE / FEEDBACK MEMORY ----------------

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal TEXT NOT NULL,
                score REAL NOT NULL,
                entry REAL NOT NULL,
                outcome TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

def save_feedback(symbol, signal, score, entry, outcome):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            """INSERT INTO feedback
            (symbol, signal, score, entry, outcome, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                symbol, signal, float(score), float(entry), outcome,
                datetime.now(timezone.utc).isoformat()
            )
        )

def get_feedback(symbol=None):
    with sqlite3.connect(DB_PATH) as con:
        if symbol:
            df = pd.read_sql_query(
                "SELECT * FROM feedback WHERE symbol=? ORDER BY id DESC",
                con, params=(symbol,)
            )
        else:
            df = pd.read_sql_query(
                "SELECT * FROM feedback ORDER BY id DESC", con
            )
    return df

init_db()

# ---------------- MARKET DATA ----------------

@st.cache_data(ttl=60, show_spinner=False)
def get_market_data(symbol, period, interval):
    df = yf.download(
        symbol,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
        threads=False
    )
    if df.empty:
        return pd.DataFrame()

    # Handle newer yfinance MultiIndex column format.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in required):
        return pd.DataFrame()

    df = df[required].copy()
    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["Open", "High", "Low", "Close"])

# ---------------- BOT 1: NEWS INTELLIGENCE ----------------

@st.cache_data(ttl=600, show_spinner=False)
def fetch_news(symbol, company_name=""):
    query = quote_plus(f'"{symbol}" {company_name} stock dividend results board meeting')
    url = (
        "https://news.google.com/rss/search?q="
        + query + "&hl=en-IN&gl=IN&ceid=IN:en"
    )
    response = requests.get(
        url, timeout=15,
        headers={"User-Agent": "Mozilla/5.0 TradingResearchApp/1.0"}
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    rows = []
    for item in feed.entries[:15]:
        rows.append({
            "Headline": item.get("title", "No title"),
            "Published": item.get("published", "Date unavailable"),
            "Source": item.get("source", {}).get("title", "News source"),
            "Link": item.get("link", "")
        })
    return rows

def render_news(symbol, company_name):
    st.subheader("Bot 1 — Market Intelligence & News")
    st.caption("వార్తల హెడ్‌లైన్‌లు మాత్రమే కంపెనీ ప్రకటనలకు ప్రత్యామ్నాయం కావు.")
    try:
        news = fetch_news(symbol, company_name)
        if not news:
            st.info("వార్తలు అందుబాటులో లేవు.")
        for item in news:
            st.markdown(f"**{item['Headline']}**")
            st.caption(f"{item['Published']} · {item['Source']}")
            if item["Link"]:
                st.markdown(f"[వార్తను చదవండి]({item['Link']})")
            st.divider()
    except Exception as exc:
        st.error(f"వార్తలు పొందలేకపోయాం: {exc}")

# ---------------- BOT 2: GEMINI CHART VISION ----------------

def ask_gemini(prompt, image_bytes=None, mime_type="image/png"):
    api_key = (
        st.session_state.get("gemini_key", "").strip()
        or os.getenv("GEMINI_API_KEY", "").strip()
    )
    if not api_key:
        raise ValueError(
            "Gemini API key ఇవ్వండి లేదా Render‌లో GEMINI_API_KEY "
            "environment variable సెట్ చేయండి."
        )

    parts = [{"text": prompt}]
    if image_bytes:
        import base64
        parts.append({
            "inline_data": {
                "mime_type": mime_type,
                "data": base64.b64encode(image_bytes).decode("utf-8")
            }
        })

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + GEMINI_MODEL + ":generateContent"
    )
    response = requests.post(
        url,
        params={"key": api_key},
        json={"contents": [{"parts": parts}]},
        timeout=60
    )
    if not response.ok:
        raise RuntimeError(
            f"Gemini API error {response.status_code}: "
            f"{response.text[:600]}"
        )
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

def render_chart_bot():
    st.subheader("Bot 2 — Visual Chart & Pattern Bot")
    upload = st.file_uploader(
        "Intraday / F&O చార్ట్ స్క్రీన్‌షాట్ అప్‌లోడ్ చేయండి",
        type=["png", "jpg", "jpeg"],
        key="chart_upload"
    )
    if upload:
        try:
            image_bytes = upload.getvalue()
            img = Image.open(io.BytesIO(image_bytes))
            st.image(img, caption="మీరు అప్‌లోడ్ చేసిన చార్ట్", use_container_width=True)
            if st.button("చార్ట్ విశ్లేషించు", key="analyze_chart"):
                with st.spinner("చార్ట్‌ను విశ్లేషిస్తున్నాం..."):
                    result = ask_gemini(
                        "Analyze this trading chart screenshot. Identify visible "
                        "trend, candlestick patterns, possible support/resistance, "
                        "breakout/reversal evidence and uncertainty. Never invent "
                        "prices that are not legible. Separate observation from "
                        "speculation. Do not claim certainty or guarantee profits. "
                        "State that this is educational analysis.",
                        image_bytes,
                        upload.type or "image/png"
                    )
                    st.markdown(result)
        except Exception as exc:
            st.error(f"చార్ట్ విశ్లేషణ విఫలమైంది: {exc}")

# ---------------- BOT 3: TECHNICAL INDICATORS ----------------

def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def atr(df, period=10):
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def calculate_indicators(df):
    x = df.copy()
    close, high, low, volume = x["Close"], x["High"], x["Low"], x["Volume"]

    # Moving averages and trend
    for p in [5, 9, 10, 20, 21, 50, 100, 200]:
        x[f"SMA_{p}"] = close.rolling(p).mean()
        x[f"EMA_{p}"] = close.ewm(span=p, adjust=False).mean()

    # RSI
    x["RSI_14"] = rsi(close)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    x["MACD"] = ema12 - ema26
    x["MACD_Signal"] = x["MACD"].ewm(span=9, adjust=False).mean()
    x["MACD_Hist"] = x["MACD"] - x["MACD_Signal"]

    # Bollinger Bands
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    x["BB_Middle"] = mid
    x["BB_Upper"] = mid + 2 * std
    x["BB_Lower"] = mid - 2 * std
    x["BB_Width"] = (x["BB_Upper"] - x["BB_Lower"]) / mid.replace(0, np.nan)

    # ATR and Supertrend
    x["ATR_14"] = atr(x, 14)
    st_atr = atr(x, 10)
    hl2 = (high + low) / 2
    upper = hl2 + 3 * st_atr
    lower = hl2 - 3 * st_atr
    final_upper = upper.copy()
    final_lower = lower.copy()
    trend = pd.Series(index=x.index, dtype=float)
    for i in range(len(x)):
        if i == 0:
            trend.iloc[i] = 1
            continue
        if upper.iloc[i] < final_upper.iloc[i-1] or close.iloc[i-1] > final_upper.iloc[i-1]:
            final_upper.iloc[i] = upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i-1]
        if lower.iloc[i] > final_lower.iloc[i-1] or close.iloc[i-1] < final_lower.iloc[i-1]:
            final_lower.iloc[i] = lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i-1]
        if trend.iloc[i-1] == 1:
            trend.iloc[i] = -1 if close.iloc[i] < final_lower.iloc[i] else 1
        else:
            trend.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1
    x["Supertrend"] = np.where(trend == 1, final_lower, final_upper)
    x["Supertrend_Direction"] = trend

    # Stochastic oscillator
    lowest = low.rolling(14).min()
    highest = high.rolling(14).max()
    denom = (highest - lowest).replace(0, np.nan)
    x["Stoch_K"] = 100 * (close - lowest) / denom
    x["Stoch_D"] = x["Stoch_K"].rolling(3).mean()

    # VWAP (cumulative within the downloaded period; intraday use is preferred)
    typical = (high + low + close) / 3
    cumulative_volume = volume.fillna(0).cumsum()
    x["VWAP"] = (
        (typical * volume.fillna(0)).cumsum()
        / cumulative_volume.replace(0, np.nan)
    )

    # Other common indicators
    x["ROC_10"] = close.pct_change(10) * 100
    x["Momentum_10"] = close - close.shift(10)
    x["CCI_20"] = (
        (typical - typical.rolling(20).mean())
        / (0.015 * typical.rolling(20).apply(
            lambda a: np.mean(np.abs(a - np.mean(a))), raw=True
        ).replace(0, np.nan))
    )
    x["Williams_R"] = -100 * (highest - close) / denom
    x["OBV"] = (np.sign(close.diff()).fillna(0) * volume.fillna(0)).cumsum()
    x["ADX_TR"] = x["ATR_14"]
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    x["DI_Plus"] = 100 * plus_dm.ewm(alpha=1/14, adjust=False).mean() / x["ATR_14"].replace(0, np.nan)
    x["DI_Minus"] = 100 * minus_dm.ewm(alpha=1/14, adjust=False).mean() / x["ATR_14"].replace(0, np.nan)
    dx = 100 * (x["DI_Plus"] - x["DI_Minus"]).abs() / (
        x["DI_Plus"] + x["DI_Minus"]
    ).replace(0, np.nan)
    x["ADX_14"] = dx.ewm(alpha=1/14, adjust=False).mean()

    # Candle structure
    x["Candle_Body"] = (close - x["Open"]).abs()
    x["Upper_Wick"] = high - pd.concat([x["Open"], close], axis=1).max(axis=1)
    x["Lower_Wick"] = pd.concat([x["Open"], close], axis=1).min(axis=1) - low

    return x.replace([np.inf, -np.inf], np.nan)

def analyze_signal(x, symbol):
    last = x.iloc[-1]
    previous = x.iloc[-2] if len(x) > 1 else last
    price = float(last["Close"])
    score = 0
    reasons = []

    def val(name):
        return last.get(name, np.nan)

    # Trend alignment
    if pd.notna(val("EMA_20")) and pd.notna(val("EMA_50")):
        if val("EMA_20") > val("EMA_50"):
            score += 1
            reasons.append("EMA 20 > EMA 50: bullish trend")
        else:
            score -= 1
            reasons.append("EMA 20 < EMA 50: bearish trend")

    # RSI
    if pd.notna(val("RSI_14")):
        if val("RSI_14") > 55:
            score += 1
            reasons.append("RSI momentum bullish")
        elif val("RSI_14") < 45:
            score -= 1
            reasons.append("RSI momentum bearish")

    # MACD crossover / alignment
    if pd.notna(val("MACD")) and pd.notna(val("MACD_Signal")):
        if val("MACD") > val("MACD_Signal"):
            score += 1
            reasons.append("MACD above signal")
        else:
            score -= 1
            reasons.append("MACD below signal")

    # Supertrend
    if pd.notna(val("Supertrend_Direction")):
        if val("Supertrend_Direction") > 0:
            score += 1
            reasons.append("Supertrend bullish")
        else:
            score -= 1
            reasons.append("Supertrend bearish")

    # VWAP
    if pd.notna(val("VWAP")):
        if price > val("VWAP"):
            score += 1
            reasons.append("Price above calculated VWAP")
        else:
            score -= 1
            reasons.append("Price below calculated VWAP")

    # Stochastic momentum
    if pd.notna(val("Stoch_K")) and pd.notna(val("Stoch_D")):
        if val("Stoch_K") > val("Stoch_D"):
            score += 1
            reasons.append("Stochastic K above D")
        elif val("Stoch_K") < val("Stoch_D"):
            score -= 1
            reasons.append("Stochastic K below D")

    # ADX trend strength
    if pd.notna(val("ADX_14")):
        reasons.append(f"ADX: {val('ADX_14'):.1f} (trend strength, not direction)")

    # Early warning: squeeze / proximity to recent range boundaries
    recent = x.tail(20)
    resistance = float(recent["High"].max())
    support = float(recent["Low"].min())
    near_resistance = resistance > 0 and (resistance - price) / resistance < 0.005
    near_support = support > 0 and (price - support) / price < 0.005
    squeeze = (
        len(x) > 20 and pd.notna(val("BB_Width"))
        and val("BB_Width") < x["BB_Width"].tail(100).quantile(0.25)
    )

    if score >= 3:
        signal = "BULLISH BIAS"
    elif score <= -3:
        signal = "BEARISH BIAS"
    else:
        signal = "MIXED / WAIT"

    warnings = []
    if near_resistance:
        warnings.append("ధర ఇటీవలి రెసిస్టెన్స్‌కు దగ్గరగా ఉంది; బ్రేక్‌అవుట్ నిర్ధారణ కాలేదు.")
    if near_support:
        warnings.append("ధర ఇటీవలి సపోర్ట్‌కు దగ్గరగా ఉంది; బ్రేక్‌డౌన్ నిర్ధారణ కాలేదు.")
    if squeeze:
        warnings.append("Bollinger Band squeeze కనిపిస్తోంది; దిశ ఇంకా నిర్ధారణ కాలేదు.")

    return {
        "symbol": symbol,
        "price": price,
        "score": score,
        "signal": signal,
        "reasons": reasons,
        "support": support,
        "resistance": resistance,
        "warnings": warnings,
        "rsi": val("RSI_14"),
        "macd": val("MACD"),
        "macd_signal": val("MACD_Signal"),
        "bb_upper": val("BB_Upper"),
        "bb_lower": val("BB_Lower"),
        "vwap": val("VWAP"),
        "adx": val("ADX_14"),
        "squeeze": squeeze
    }

def render_speaker(text):
    # Speech synthesis runs in the user's browser.
    safe_text = json.dumps(text, ensure_ascii=False)
    components.html(
        f"""
        <button onclick='speakAlert()'
          style="padding:10px 16px;font-size:16px;cursor:pointer">
          🔊 వాయిస్ అలర్ట్ వినండి
        </button>
        <script>
          const message = {safe_text};
          function speakAlert() {{
            if (!("speechSynthesis" in window)) {{
              alert("ఈ బ్రౌజర్‌లో వాయిస్ సపోర్ట్ లేదు.");
              return;
            }}
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(message);
            utterance.lang = "te-IN";
            utterance.rate = 0.9;
            window.speechSynthesis.speak(utterance);
          }}
        </script>
        """,
        height=65
    )

def render_indicator_bot(symbol, df):
    st.subheader("Bot 3 — Multi-Indicator & Predictive Signals")
    if len(df) < 30:
        st.error("సూచికల విశ్లేషణకు కనీసం 30 క్యాండిల్స్ అవసరం.")
        return

    x = calculate_indicators(df)
    result = analyze_signal(x, symbol)

    col1, col2, col3 = st.columns(3)
    col1.metric("చివరి ధర", f"{result['price']:.2f}")
    col2.metric("సిగ్నల్ స్కోర్", f"{result['score']:+d} / 6")
    col3.metric("RSI (14)", f"{result['rsi']:.2f}" if pd.notna(result["rsi"]) else "N/A")

    st.markdown(f"### సంకేతం: {result['signal']}")
    st.caption(
        "స్కోర్ అనేది ఆరు నియమాల ఆధారంగా లెక్కించిన సూచిక మాత్రమే; "
        "ఇది గెలుపు శాతం లేదా నిర్ధారిత probability కాదు."
    )

    st.write("**సంకేతానికి కారణాలు**")
    for reason in result["reasons"]:
        st.write(f"- {reason}")

    st.write(
        f"**20 క్యాండిల్స్ సపోర్ట్ పరిధి:** {result['support']:.2f}  \n"
        f"**20 క్యాండిల్స్ రెసిస్టెన్స్ పరిధి:** {result['resistance']:.2f}"
    )
    for warning in result["warnings"]:
        st.warning(warning)

    display_cols = [
        "Close", "RSI_14", "EMA_20", "EMA_50", "MACD",
        "MACD_Signal", "BB_Upper", "BB_Lower", "Supertrend",
        "VWAP", "Stoch_K", "Stoch_D", "ADX_14", "ATR_14",
        "CCI_20", "Williams_R", "OBV"
    ]
    st.write("**తాజా సూచికల విలువలు**")
    st.dataframe(
        x[[c for c in display_cols if c in x.columns]].tail(10),
        use_container_width=True
    )

    st.write("**ధర చార్ట్**")
    st.line_chart(x[["Close", "EMA_20", "EMA_50", "BB_Upper", "BB_Lower"]])

    alert = (
        f"{symbol}. {result['signal']}. "
        f"ధర {result['price']:.2f}. స్కోర్ {result['score']}."
    )
    render_speaker(alert)

    st.markdown("#### గత సంకేతాల ఫలితాన్ని నమోదు చేయండి")
    st.caption(
        "ఇది మానవ సమీక్ష ఆధారిత feedback. నిజమైన predictive learning కోసం "
        "సమయానుసారమైన entry/exit ధరలు, transaction costs, slippage కూడా నమోదు చేయాలి."
    )
    with st.form("feedback_form"):
        outcome = st.selectbox(
            "ఈ సంకేతం తర్వాత మీ సమీక్ష",
            ["Correct", "Incorrect", "Unclear"]
        )
        submitted = st.form_submit_button("ఫలితాన్ని సేవ్ చేయండి")
        if submitted:
            save_feedback(
                symbol, result["signal"], result["score"],
                result["price"], outcome
            )
            st.success("ఫీడ్‌బ్యాక్ సేవ్ అయింది.")

    memory = get_feedback(symbol)
    if not memory.empty:
        scored = memory[memory["outcome"].isin(["Correct", "Incorrect"])]
        st.metric("నమోదు చేసిన సమీక్షలు", len(memory))
        if not scored.empty:
            accuracy = (scored["outcome"] == "Correct").mean() * 100
            st.metric("గత సమీక్షల్లో సరైనవి", f"{accuracy:.1f}%")
        st.dataframe(memory.head(20), use_container_width=True)

# ---------------- APP CONTROLS ----------------

with st.sidebar:
    st.header("సెట్టింగ్స్")
    symbol = st.text_input("స్టాక్ టికర్", value="RELIANCE.NS").strip().upper()
    company_name = st.text_input("కంపెనీ పేరు (ఐచ్ఛికం)", value="")
    period = st.selectbox("డేటా కాలం", ["1mo", "3mo", "6mo", "1y", "2y"], index=2)
    interval = st.selectbox("క్యాండిల్ టైమ్‌ఫ్రేమ్", ["5m", "15m", "30m", "60m", "1d"], index=3)
    st.caption(
        "Yahoo Financeలో intraday చరిత్ర పరిమితం కావచ్చు. "
        "అందుబాటులో లేని టైమ్‌ఫ్రేమ్‌కు డేటా రాకపోవచ్చు."
    )
    with st.expander("Gemini API Key"):
        st.text_input(
            "ఈ సెషన్‌కు API key",
            type="password",
            key="gemini_key"
        )
        st.caption(
            "ఈ బాక్స్‌లో ఇచ్చిన key ఈ Streamlit సెషన్‌కే ఉంటుంది. "
            "శాశ్వతంగా సెట్ చేయడానికి Render Environment Variables వాడండి."
        )

if not symbol:
    st.stop()

tabs = st.tabs(["📊 Technical Bot", "📰 News Bot", "🖼️ Chart Bot", "ℹ️ About"])
with tabs[0]:
    try:
        with st.spinner("మార్కెట్ డేటా పొందుతున్నాం..."):
            market_df = get_market_data(symbol, period, interval)
       
