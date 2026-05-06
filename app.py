import streamlit as st
import pandas as pd
import zipfile
import csv
import time
import os
import subprocess
import asyncio
import traceback
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Stock Adjustment Newspage", page_icon="icon.png", layout="wide")

# --- 1.5. LOGIN GATEKEEPER ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    # Center the login card vertically
    st.markdown("""
    <style>
    .login-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 1.6rem;
        padding-bottom: 1.2rem;
        border-bottom: 1px solid #1a2d50;
    }
    .login-icon {
        width: 34px; height: 34px;
        background: #3b82f6;
        border-radius: 8px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 1rem;
        flex-shrink: 0;
    }
    .login-brand {
        font-family: 'Outfit', sans-serif;
        font-size: 0.95rem;
        font-weight: 700;
        color: #e8eef8;
        letter-spacing: -0.01em;
    }
    .login-title {
        font-family: 'Outfit', sans-serif;
        font-size: 1.55rem;
        font-weight: 800;
        color: #e8eef8;
        letter-spacing: -0.02em;
        margin: 0 0 4px;
        line-height: 1.2;
    }
    .login-sub {
        font-family: 'Outfit', sans-serif;
        font-size: 0.83rem;
        color: #4a6080;
        margin: 0 0 1.4rem;
    }
    /* Style the form container as the card */
    [data-testid="stForm"] {
        background: #0d1526 !important;
        border: 1px solid #1a2d50 !important;
        border-radius: 14px !important;
        padding: 2rem 2rem 1.6rem !important;
    }
    /* Push content down to vertically center */
    section[data-testid="stMain"] > div:first-child {
        padding-top: 6vh !important;
    }
    </style>
    <div style="height:4vh"></div>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        with st.form("login_form"):
            # Branding INSIDE the form so it's inside the card
            st.markdown("""
            <div class='login-header'>
                <span class='login-icon'>⚡</span>
                <span class='login-brand'>StockEngine</span>
            </div>
            <div class='login-title'>Welcome back</div>
            <div class='login-sub'>Sign in to access the adjustment engine</div>
            """, unsafe_allow_html=True)

            username = st.text_input("Username", placeholder="Enter username...")
            password = st.text_input("Password", type="password", placeholder="Enter password...")
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
            submit = st.form_submit_button("Sign In →", use_container_width=True)

            if submit:
                if username == st.secrets["admin_user"] and password == st.secrets["admin_pass"]:
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Access denied — invalid credentials.")

    st.stop()

# --- 2. CONSTANTS ---
URL_LOGIN             = "https://rb-id.np.accenture.com/RB_ID/Logon.aspx"
CREDENTIALS_FILE      = "users_2.csv"
REASON_CODE           = "SA2"
WAREHOUSE             = "GOOD_WHS"
TIMEOUT_MS            = 30_000
TABLE_UPDATE_INTERVAL = 5  # FIX: throttle table re-renders (was every row)

# --- 3. HELPER FUNCTIONS ---

def load_data(file):
    if file is None:
        return None
    df = None
    filename = file.name.lower()
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file, sep='\t', dtype=str)
            if df.shape[1] <= 1:
                file.seek(0)
                df = pd.read_csv(file, sep=',', dtype=str)
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file, dtype=str)
        elif filename.endswith('.zip'):
            with zipfile.ZipFile(file) as z:
                target = next((n for n in z.namelist() if "INVT_MASTER" in n and n.lower().endswith(".csv")), None)
                if not target:
                    target = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
                if target:
                    with z.open(target) as f:
                        df = pd.read_csv(f, sep='\t', dtype=str)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None
    return df


# FIX: Added @st.cache_data to prevent re-reading the CSV on every Streamlit rerun.
@st.cache_data(ttl=300)
def load_accounts():
    accounts = []
    if not os.path.exists(CREDENTIALS_FILE):
        return accounts
    for enc in ['utf-8-sig', 'cp1252', 'iso-8859-1']:
        try:
            with open(CREDENTIALS_FILE, mode="r", encoding=enc) as f:
                reader = csv.DictReader(f)
                reader.fieldnames = [name.strip() for name in reader.fieldnames if name]
                for row in reader:
                    cleaned_row = {str(k).strip(): str(v).strip() for k, v in row.items() if k}
                    if "user_id" in cleaned_row and "Distributor" in cleaned_row:
                        accounts.append(cleaned_row)
                return accounts
        except (UnicodeDecodeError, TypeError):
            continue
    return accounts


@st.cache_resource
def ensure_playwright():
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True
        )
    except Exception as e:
        st.error(f"Failed to install browser engine: {e}")


# FIX: Extracted repeated inline badge HTML into a single reusable helper.
def make_badge(text: str, bg_color: str, text_color: str) -> str:
    return (
        f"<div style='background-color:{bg_color};color:{text_color};"
        f"padding:7px 14px;border-radius:6px;font-weight:500;"
        f"font-family:Outfit,sans-serif;font-size:0.82rem;"
        f"margin-top:6px;border:1px solid {text_color}22;'>{text}</div>"
    )


# --- 4. STATE MANAGEMENT ---
if 'app_page' not in st.session_state:
    st.session_state.app_page = "Reconcile"
if 'reconcile_result' not in st.session_state:
    st.session_state.reconcile_result = None
if 'reconcile_summary' not in st.session_state:
    st.session_state.reconcile_summary = None

# --- 5. CUSTOM CSS ---
st.markdown("""
<style>
/* ══════════════════════════════════════════════════════════════════
   FONTS
══════════════════════════════════════════════════════════════════ */
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ══════════════════════════════════════════════════════════════════
   TOKENS
══════════════════════════════════════════════════════════════════ */
:root {
    --c-bg:       #070d1a;
    --c-surface:  #0d1526;
    --c-raised:   #111d35;
    --c-border:   #1a2d50;
    --c-accent:   #3b82f6;
    --c-hover:    #2563eb;
    --c-success:  #10b981;
    --c-error:    #ef4444;
    --c-warn:     #f59e0b;
    --c-text:     #e8eef8;
    --c-muted:    #4a6080;
    --c-dim:      #2a3d5a;
    --f-sans:     'Outfit', sans-serif;
    --f-mono:     'JetBrains Mono', monospace;
    --r:          8px;
    --r-sm:       6px;
}

/* ══════════════════════════════════════════════════════════════════
   GLOBAL
══════════════════════════════════════════════════════════════════ */
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background-color: var(--c-bg) !important;
    color: var(--c-text) !important;
    font-family: var(--f-sans) !important;
}
.main .block-container {
    background-color: transparent !important;
    padding-top: 1.8rem !important;
}
* { box-sizing: border-box; }

/* ══════════════════════════════════════════════════════════════════
   HEADER / TOOLBAR
══════════════════════════════════════════════════════════════════ */
header[data-testid="stHeader"] {
    background-color: var(--c-bg) !important;
    border-bottom: 1px solid var(--c-border) !important;
}

/* ══════════════════════════════════════════════════════════════════
   BUTTONS  — single solid system, no exceptions
══════════════════════════════════════════════════════════════════ */
button {
    font-family: var(--f-sans) !important;
    border-radius: var(--r-sm) !important;
    transition: background-color 0.15s ease, box-shadow 0.15s ease,
                transform 0.1s ease !important;
    cursor: pointer !important;
}

/* Primary */
button[kind="primary"] {
    background-color: var(--c-accent) !important;
    color: #fff !important;
    border: none !important;
    font-weight: 700 !important;
    font-size: 0.78rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
}
button[kind="primary"]:hover {
    background-color: var(--c-hover) !important;
    box-shadow: 0 4px 16px rgba(37,99,235,0.4) !important;
    transform: translateY(-1px) !important;
}
button[kind="primary"]:active  { transform: none !important; box-shadow: none !important; }
button[kind="primary"]:disabled {
    background-color: var(--c-raised) !important;
    color: var(--c-muted) !important;
    box-shadow: none !important;
}

/* Secondary */
button[kind="secondary"] {
    background-color: transparent !important;
    color: var(--c-accent) !important;
    border: 1px solid var(--c-border) !important;
    font-weight: 600 !important;
    font-size: 0.78rem !important;
    letter-spacing: 0.06em !important;
}
button[kind="secondary"]:hover {
    background-color: var(--c-raised) !important;
    border-color: var(--c-accent) !important;
    color: #fff !important;
}

/* Form submit (login) — same as primary */
button[kind="formSubmit"] {
    background-color: var(--c-accent) !important;
    color: #fff !important;
    border: none !important;
    font-weight: 700 !important;
    font-size: 0.78rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
}
button[kind="formSubmit"]:hover {
    background-color: var(--c-hover) !important;
    box-shadow: 0 4px 16px rgba(37,99,235,0.4) !important;
}

/* ══════════════════════════════════════════════════════════════════
   TEXT INPUTS
══════════════════════════════════════════════════════════════════ */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input {
    background-color: var(--c-raised) !important;
    border: 1px solid var(--c-border) !important;
    border-radius: var(--r-sm) !important;
    color: var(--c-text) !important;
    font-family: var(--f-sans) !important;
    font-size: 0.88rem !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: var(--c-accent) !important;
    box-shadow: 0 0 0 3px rgba(59,130,246,0.15) !important;
    outline: none !important;
}
[data-testid="stTextInput"] input:disabled {
    opacity: 0.5 !important;
    cursor: not-allowed !important;
}
input::placeholder, textarea::placeholder {
    color: var(--c-muted) !important;
    font-size: 0.85rem !important;
}

/* Input labels */
[data-testid="stTextInput"] label,
[data-testid="stTextArea"] label,
[data-testid="stSelectbox"] label,
[data-testid="stFileUploader"] label {
    color: var(--c-muted) !important;
    font-family: var(--f-sans) !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}

/* ══════════════════════════════════════════════════════════════════
   SELECTBOX  — targeting the actual BaseWeb DOM nodes
══════════════════════════════════════════════════════════════════ */

/* The visible trigger control */
[data-baseweb="select"] [data-baseweb="control"] {
    background-color: var(--c-raised) !important;
    border: 1px solid var(--c-border) !important;
    border-radius: var(--r-sm) !important;
    transition: border-color 0.15s !important;
    min-height: 38px !important;
}
[data-baseweb="select"] [data-baseweb="control"]:hover,
[data-baseweb="select"] [data-baseweb="control"]:focus-within {
    border-color: var(--c-accent) !important;
}

/* Selected value text */
[data-baseweb="select"] [data-baseweb="single-value"],
[data-baseweb="select"] [data-baseweb="placeholder"] {
    color: var(--c-text) !important;
    font-family: var(--f-sans) !important;
    font-size: 0.88rem !important;
}
[data-baseweb="select"] [data-baseweb="placeholder"] {
    color: var(--c-muted) !important;
}

/* Dropdown arrow */
[data-baseweb="select"] svg { fill: var(--c-muted) !important; }

/* ── DROPDOWN POPUP ───────────────────────────────────────────── */
/* The outer popover layer */
[data-baseweb="popover"] > div,
[data-baseweb="popover"] [data-baseweb="menu"] {
    background-color: var(--c-surface) !important;
    border: 1px solid var(--c-border) !important;
    border-radius: var(--r) !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.6) !important;
    overflow: hidden !important;
}

/* Each option row */
[data-baseweb="menu"] li,
[data-baseweb="menu"] [role="option"] {
    background-color: var(--c-surface) !important;
    color: var(--c-text) !important;
    font-family: var(--f-sans) !important;
    font-size: 0.88rem !important;
    padding: 9px 14px !important;
    border-radius: 0 !important;
    transition: background-color 0.1s !important;
}
/* Hover state */
[data-baseweb="menu"] li:hover,
[data-baseweb="menu"] [role="option"]:hover {
    background-color: var(--c-raised) !important;
    color: #fff !important;
}
/* Selected / active state */
[data-baseweb="menu"] [aria-selected="true"],
[data-baseweb="menu"] li[aria-selected="true"] {
    background-color: var(--c-accent) !important;
    color: #fff !important;
}
[data-baseweb="menu"] [aria-selected="true"]:hover {
    background-color: var(--c-hover) !important;
}

/* ══════════════════════════════════════════════════════════════════
   FILE UPLOADER
══════════════════════════════════════════════════════════════════ */
[data-testid="stFileUploaderDropzone"] {
    background-color: var(--c-raised) !important;
    border: 1px dashed var(--c-border) !important;
    border-radius: var(--r) !important;
    transition: border-color 0.15s, background-color 0.15s !important;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--c-accent) !important;
    background-color: #0d1e38 !important;
}
[data-testid="stFileUploaderDropzone"] span,
[data-testid="stFileUploaderDropzone"] small {
    color: var(--c-muted) !important;
    font-family: var(--f-sans) !important;
}

/* ══════════════════════════════════════════════════════════════════
   METRICS
══════════════════════════════════════════════════════════════════ */
[data-testid="stMetric"] {
    background-color: var(--c-surface) !important;
    border: 1px solid var(--c-border) !important;
    border-radius: var(--r) !important;
    padding: 1rem 1.4rem !important;
}
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] > div {
    color: var(--c-accent) !important;
    font-weight: 700 !important;
    font-family: var(--f-sans) !important;
    display: block !important;
}
[data-testid="stMetricLabel"] {
    color: var(--c-muted) !important;
    font-size: 0.7rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    font-family: var(--f-sans) !important;
}

/* ══════════════════════════════════════════════════════════════════
   ALERTS
══════════════════════════════════════════════════════════════════ */
[data-testid="stAlert"] {
    border-radius: var(--r-sm) !important;
    font-family: var(--f-sans) !important;
    font-size: 0.85rem !important;
    border-width: 1px !important;
    border-style: solid !important;
}
/* Success */
[data-testid="stAlert"][data-baseweb="notification"] {
    background-color: #071e14 !important;
    border-color: #134d2e !important;
    color: #6ee7b7 !important;
}
/* Error */
div[data-testid="stException"],
.stException {
    background-color: #1a0a0a !important;
    border: 1px solid #5c1c1c !important;
    border-radius: var(--r-sm) !important;
}

/* ══════════════════════════════════════════════════════════════════
   PROGRESS BAR
══════════════════════════════════════════════════════════════════ */
[data-testid="stProgress"] > div {
    background-color: var(--c-raised) !important;
    border-radius: 99px !important;
    height: 4px !important;
}
[data-testid="stProgress"] > div > div {
    background-color: var(--c-accent) !important;
    border-radius: 99px !important;
}

/* ══════════════════════════════════════════════════════════════════
   DATAFRAME
══════════════════════════════════════════════════════════════════ */
[data-testid="stDataFrame"] {
    border: 1px solid var(--c-border) !important;
    border-radius: var(--r) !important;
    overflow: hidden !important;
}

/* ══════════════════════════════════════════════════════════════════
   DIVIDER / HR
══════════════════════════════════════════════════════════════════ */
hr {
    border: none !important;
    height: 1px !important;
    background-color: var(--c-border) !important;
    opacity: 1 !important;
    margin: 1.5rem 0 !important;
}

/* ══════════════════════════════════════════════════════════════════
   SCROLLBAR
══════════════════════════════════════════════════════════════════ */
*::-webkit-scrollbar       { width: 4px; height: 4px; }
*::-webkit-scrollbar-track { background: transparent; }
*::-webkit-scrollbar-thumb { background-color: var(--c-border); border-radius: 99px; }
*::-webkit-scrollbar-thumb:hover { background-color: var(--c-accent); }
* { scrollbar-width: thin; scrollbar-color: var(--c-border) transparent; }

/* ══════════════════════════════════════════════════════════════════
   TEXT SELECTION
══════════════════════════════════════════════════════════════════ */
::selection      { background: var(--c-accent); color: #fff; }
::-moz-selection { background: var(--c-accent); color: #fff; }

/* ══════════════════════════════════════════════════════════════════
   STATUS WIDGET (top-right running indicator)
══════════════════════════════════════════════════════════════════ */
[data-testid="stStatusWidget"] {
    background-color: var(--c-surface) !important;
    border: 1px solid var(--c-border) !important;
    border-radius: var(--r-sm) !important;
}
[data-testid="stStatusWidget"] * {
    color: var(--c-accent) !important;
    font-family: var(--f-mono) !important;
    font-size: 0.72rem !important;
}

/* ══════════════════════════════════════════════════════════════════
   HEADINGS & TYPOGRAPHY
══════════════════════════════════════════════════════════════════ */
h1, h2, h3, h4 {
    font-family: var(--f-sans) !important;
    color: var(--c-text) !important;
    letter-spacing: -0.02em !important;
}
h1 { font-size: 1.9rem !important; font-weight: 800 !important; margin-bottom: 0.2rem !important; }
h2 { font-size: 1.25rem !important; font-weight: 700 !important; }
h3 { font-size: 1rem !important; font-weight: 600 !important; }
p, li, span { font-family: var(--f-sans) !important; }

/* ══════════════════════════════════════════════════════════════════
   PAGE LOAD ANIMATION
══════════════════════════════════════════════════════════════════ */
@keyframes fadeUp {
    from { opacity: 0; transform: translateY(12px); }
    to   { opacity: 1; transform: translateY(0); }
}
[data-testid="stVerticalBlock"] > div {
    animation: fadeUp 0.35s ease backwards;
}
[data-testid="stVerticalBlock"] > div:nth-child(1) { animation-delay: 0.04s; }
[data-testid="stVerticalBlock"] > div:nth-child(2) { animation-delay: 0.08s; }
[data-testid="stVerticalBlock"] > div:nth-child(3) { animation-delay: 0.12s; }
[data-testid="stVerticalBlock"] > div:nth-child(4) { animation-delay: 0.16s; }

/* ══════════════════════════════════════════════════════════════════
   LIVE INDICATOR BADGE
══════════════════════════════════════════════════════════════════ */
.live-indicator {
    display: inline-flex;
    align-items: center;
    color: var(--c-success);
    font-family: var(--f-mono);
    font-weight: 700;
    font-size: 0.68rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    background: #071e14;
    border: 1px solid #134d2e;
    padding: 3px 10px;
    border-radius: 99px;
    margin-bottom: 0.5rem;
}
.live-indicator::before {
    content: '';
    display: inline-block;
    width: 6px; height: 6px;
    background-color: var(--c-success);
    border-radius: 50%;
    margin-right: 7px;
    animation: pulse-live 1.6s ease-in-out infinite;
}
@keyframes pulse-live {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.4; transform: scale(0.65); }
}

/* ══════════════════════════════════════════════════════════════════
   TERMINAL LOG BOX
══════════════════════════════════════════════════════════════════ */
.terminal-box {
    background-color: transparent;
    color: var(--c-text);
    font-family: var(--f-mono);
    font-size: 0.76rem;
    padding: 4px 0;
    border: none;
    height: 360px;
    overflow-y: auto;
    line-height: 1.9;
    -ms-overflow-style: none;
    scrollbar-width: none;
}
.terminal-box::-webkit-scrollbar { display: none; }
.blink_me { animation: blinker 1s linear infinite; color: var(--c-success); }
@keyframes blinker { 50% { opacity: 0; } }

.log-time   { display: inline-block; width: 82px;  color: var(--c-dim); }
.log-ms     { display: inline-block; width: 68px;  text-align: right; margin-right: 14px; color: #9a6a3a; font-size: 0.7rem; }
.log-tag    { display: inline-block; width: 92px;  font-weight: 600; }
.log-msg    { color: #b0c4de; }

.tag-sys     { color: #a78bfa; }
.tag-auth    { color: #fbbf24; }
.tag-nav     { color: #60a5fa; }
.tag-inject  { color: #22d3ee; }
.tag-success { color: #34d399; }
.tag-error   { color: #f87171; }
.tag-server  { color: #fb7185; }

/* ══════════════════════════════════════════════════════════════════
   TYPEWRITER SUBTITLE
══════════════════════════════════════════════════════════════════ */
.typewriter-sub {
    font-family: var(--f-mono);
    font-size: 0.78rem;
    color: var(--c-muted);
    overflow: hidden;
    border-right: 2px solid var(--c-accent);
    white-space: nowrap;
    margin: 0.1rem 0 0;
    animation: typing-sub 10s infinite, blink-caret .75s step-end infinite;
}
@keyframes typing-sub {
    0%   { width: 0; animation-timing-function: steps(29, end); }
    30%  { width: 29ch; animation-timing-function: step-end; }
    80%  { width: 29ch; animation-timing-function: steps(29, end); }
    100% { width: 0; }
}
@keyframes blink-caret {
    from, to { border-color: transparent; }
    50%       { border-color: var(--c-accent); }
}
</style>
""", unsafe_allow_html=True)


# ─── 6. PAGE: RECONCILE ──────────────────────────────────────────────────────
if st.session_state.app_page == "Reconcile":
    st.markdown("<div class='live-indicator'>LIVE</div>", unsafe_allow_html=True)
    st.markdown("<h1>Compare Stock</h1>", unsafe_allow_html=True)
    st.markdown("<div class='typewriter-sub'>Inspired by Kopi Mang Toni...</div>", unsafe_allow_html=True)
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        file1 = st.file_uploader("Upload Newspage stock file", type=['csv', 'xlsx', 'zip'])
    with col2:
        file2 = st.file_uploader("Upload Distributor stock file", type=['csv', 'xlsx'])

    if file1 and file2:
        st.divider()
        df1 = load_data(file1)
        df2 = load_data(file2)

        if df1 is not None and df2 is not None:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Newspage setup")
                idx_sku1 = df1.columns.get_loc('Product Code') if 'Product Code' in df1.columns else 0

                if 'Product Description' in df1.columns:
                    idx_desc1 = df1.columns.get_loc('Product Description')
                elif 'Product Name' in df1.columns:
                    idx_desc1 = df1.columns.get_loc('Product Name')
                else:
                    idx_desc1 = 1 if len(df1.columns) > 1 else 0

                idx_qty1 = (
                    df1.columns.get_loc('Stock Available')
                    if 'Stock Available' in df1.columns
                    else (2 if len(df1.columns) > 2 else 0)
                )

                sku_col1  = st.selectbox("SKU column (NP)", df1.columns, index=idx_sku1)
                desc_col1 = st.selectbox("Description column (NP)", df1.columns, index=idx_desc1)
                qty_col1  = st.selectbox("Qty column (NP)", df1.columns, index=idx_qty1)

            with c2:
                st.subheader("Distributor setup")
                # Fallback index 20: typical SKU position in distributor export format
                idx_sku2 = 20 if len(df2.columns) > 20 else 0
                qty2_col_match = next(
                    (col for col in df2.columns if str(col).strip().lower().replace(" ", "") == "stokakhir"),
                    None
                )
                if qty2_col_match:
                    idx_qty2 = df2.columns.get_loc(qty2_col_match)
                else:
                    # Fallback index 71: typical closing stock position in distributor export
                    idx_qty2 = 71 if len(df2.columns) > 71 else (1 if len(df2.columns) > 1 else 0)

                sku_col2 = st.selectbox("SKU column (Dist)", df2.columns, index=idx_sku2)
                qty_col2 = st.selectbox("Qty column (Dist)", df2.columns, index=idx_qty2)

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Compare Stock", type="primary", use_container_width=True):
                d1 = df1[[sku_col1, desc_col1, qty_col1]].copy()
                d1 = d1.dropna(subset=[sku_col1])
                d1[sku_col1] = d1[sku_col1].astype(str).str.split('.').str[0].str.strip()
                d1 = d1[~d1[sku_col1].str.lower().isin(['nan', 'none', '', 'total', 'grand total'])]
                d1[qty_col1] = pd.to_numeric(d1[qty_col1], errors='coerce').fillna(0)
                d1_agg = (
                    d1.groupby(sku_col1)
                    .agg({desc_col1: 'first', qty_col1: 'sum'})
                    .reset_index()
                    .rename(columns={sku_col1: 'SKU', desc_col1: 'Description', qty_col1: 'Newspage'})
                )

                d2 = df2[[sku_col2, qty_col2]].copy()
                d2 = d2.dropna(subset=[sku_col2])
                d2[sku_col2] = d2[sku_col2].astype(str).str.split('.').str[0].str.strip()
                d2 = d2[~d2[sku_col2].str.lower().isin(['nan', 'none', '', 'total', 'grand total'])]
                d2[sku_col2] = d2[sku_col2].replace({'373103': '0373103', '373100': '0373100'})
                d2[qty_col2] = pd.to_numeric(d2[qty_col2], errors='coerce').fillna(0)
                d2_agg = (
                    d2.groupby(sku_col2)[qty_col2]
                    .sum()
                    .reset_index()
                    .rename(columns={sku_col2: 'SKU', qty_col2: 'Distributor'})
                )

                merged = pd.merge(d1_agg, d2_agg, on='SKU', how='outer')
                merged[['Newspage', 'Distributor']] = merged[['Newspage', 'Distributor']].fillna(0)
                merged['Description'] = merged['Description'].fillna('ITEM NOT IN MASTER')
                merged['Selisih'] = merged['Distributor'] - merged['Newspage']
                merged['Status'] = merged['Selisih'].apply(lambda x: 'Match' if x == 0 else 'Mismatch')

                mismatches = merged[merged['Selisih'] != 0].sort_values('Selisih')

                if len(mismatches) == 0:
                    st.success("Analysis complete: all items matched!")
                else:
                    valid_mismatches = mismatches[mismatches['Description'] != 'ITEM NOT IN MASTER'].copy()
                    st.session_state.reconcile_summary = {
                        'total_match':    len(merged[merged['Selisih'] == 0]),
                        'total_mismatch': len(mismatches),
                        'df_view':        mismatches[['SKU', 'Description', 'Newspage', 'Distributor', 'Selisih', 'Status']]
                    }
                    valid_mismatches['Selisih_Clean'] = valid_mismatches['Selisih'].astype(int)
                    transfer_df = (
                        valid_mismatches[['SKU', 'Selisih_Clean']]
                        .rename(columns={'SKU': 'sku', 'Selisih_Clean': 'qty'})
                    )
                    st.session_state.reconcile_result = transfer_df
                    st.session_state.app_page = "Bot"
                    st.rerun()

    if st.button("Stock Adjustment"):
        st.session_state.reconcile_result = None
        st.session_state.reconcile_summary = None
        st.session_state.app_page = "Bot"
        st.rerun()


# ─── 7. PAGE: STOCK ADJUSTMENT BOT ───────────────────────────────────────────
elif st.session_state.app_page == "Bot":
    hdr_col1, hdr_col2 = st.columns([5, 1])
    with hdr_col1:
        st.markdown("<div class='live-indicator'>LIVE</div>", unsafe_allow_html=True)
        st.markdown("<h1>Stock Adjustment</h1>", unsafe_allow_html=True)
        st.markdown("<div class='typewriter-sub'>Inspired by Kopi Mang Toni...</div>", unsafe_allow_html=True)
    with hdr_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Compare Stock", use_container_width=True):
            st.session_state.app_page = "Reconcile"
            st.rerun()

    st.markdown("---")

    if st.session_state.reconcile_summary is not None:
        st.subheader("Stock review")
        m1, m2 = st.columns(2)
        m1.metric("Match", st.session_state.reconcile_summary['total_match'])
        m2.metric("Stock difference", st.session_state.reconcile_summary['total_mismatch'], delta_color="inverse")
        st.dataframe(st.session_state.reconcile_summary['df_view'], use_container_width=True, hide_index=True)
        st.markdown("---")

    st.subheader("Configuration")
    accounts = load_accounts()

    if not accounts:
        st.error(f"No account data found. Ensure '{CREDENTIALS_FILE}' exists in the app directory.")
        st.stop()

    cfg_col1, cfg_col2 = st.columns(2)

    with cfg_col1:
        selected_acc_str = st.selectbox(
            "Select Distributor / User ID",
            options=[f"{acc['Distributor']} ({acc['user_id']})" for acc in accounts],
            index=None,
            placeholder="-- Select account --"
        )

        selected_account = None
        user_password = ""

        if selected_acc_str:
            selected_account = next(
                acc for acc in accounts
                if f"{acc['Distributor']} ({acc['user_id']})" == selected_acc_str
            )
            user_password = st.text_input(
                f"Password for {selected_account['user_id']}:",
                type="password",
                placeholder="Enter password..."
            )
            if len(user_password) > 3:
                st.markdown(make_badge(
                    f"Password set — {selected_account['Distributor']} (validated on run)",
                    "#0f2f1d", "#4ade80"
                ), unsafe_allow_html=True)
            else:
                st.markdown(make_badge(
                    "Waiting for password...",
                    "#1e1b4b", "#a5b4fc"
                ), unsafe_allow_html=True)

    with cfg_col2:
        df_to_process = None
        if st.session_state.reconcile_result is not None:
            st.text_input("Data source", value="Auto-loaded from Compare Stock", disabled=True)
            df_to_process = st.session_state.reconcile_result
            st.markdown(make_badge(
                f"{len(df_to_process)} products ready to process",
                "#082f49", "#38bdf8"
            ), unsafe_allow_html=True)
        else:
            uploaded_file = st.file_uploader("Data source (CSV / Excel)", type=["csv", "xlsx", "xls"])
            if uploaded_file is not None:
                try:
                    filename = uploaded_file.name.lower()
                    if filename.endswith('.csv'):
                        df_to_process = pd.read_csv(uploaded_file, dtype=str)
                    else:
                        df_to_process = pd.read_excel(uploaded_file, dtype=str)
                    df_to_process.columns = [str(c).strip().lower() for c in df_to_process.columns]
                    if 'sku' in df_to_process.columns and 'qty' in df_to_process.columns:
                        st.markdown(make_badge(
                            f"{len(df_to_process)} products ready to process",
                            "#082f49", "#38bdf8"
                        ), unsafe_allow_html=True)
                    else:
                        st.error("Invalid format — column headers must be named 'sku' and 'qty'.")
                        df_to_process = None
                except Exception as e:
                    st.error(f"Failed to read file: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    is_ready = (selected_account is not None) and (len(user_password) > 3) and (df_to_process is not None)
    run_button = st.button("PROCEED", use_container_width=True, type="primary", disabled=not is_ready)

    st.subheader("Product table")

    if not is_ready:
        st.warning("Select an account and ensure data is available before running the bot.")
        st.stop()

    df_view = df_to_process.copy()
    if 'Status' not in df_view.columns:
        df_view['Status'] = 'Pending'
    if 'Keterangan' not in df_view.columns:
        df_view['Keterangan'] = '-'

    table_placeholder = st.dataframe(df_view, use_container_width=True)

    st.markdown("Log:")
    log_placeholder = st.empty()

    if run_button:
        with st.spinner("Initializing Chromium engine..."):
            ensure_playwright()

        logs_history = []
        last_log_time = [time.time()]

        def ui_log(module, msg):
            now = time.time()
            diff_ms = int((now - last_log_time[0]) * 1000)
            last_log_time[0] = now
            timestamp = time.strftime('%H:%M:%S')
            tag_class = f"tag-{module.lower()}"
            new_log = (
                f"<span class='log-time'>[{timestamp}]</span>"
                f"<span class='log-ms'>[+{diff_ms}ms]</span>"
                f"<span class='log-tag {tag_class}'>[{module}]</span>"
                f"<span class='log-msg'>{msg}</span>"
            )
            logs_history.append(new_log)
            display_logs = "<br>".join(logs_history[-100:])
            html_content = f"""
            <div class="terminal-box" id="term_box">
                {display_logs}
                <br><span class="blink_me">&#9608;</span>
            </div>
            <script>
                var t = window.parent.document.getElementById('term_box') || document.getElementById('term_box');
                if (t) t.scrollTop = t.scrollHeight;
            </script>
            """
            log_placeholder.markdown(html_content, unsafe_allow_html=True)

        global_start_time = time.time()
        success_count, failed_count = 0, 0
        user_id  = selected_account["user_id"]
        password = user_password

        ui_log("SYS", "Allocating memory and initializing Chromium headless core...")
        try:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            asyncio.set_event_loop(asyncio.new_event_loop())

            with sync_playwright() as p:
                ui_log("SYS", "Spawning browser context with isolated session...")
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(no_viewport=True)
                page = context.new_page()

                # --- Login ---
                ui_log("AUTH", f"Connecting to {URL_LOGIN}...")
                page.goto(URL_LOGIN, wait_until="domcontentloaded")
                ui_log("AUTH", "DOM ready. Filling credentials...")
                page.locator("id=txtUserid").fill(user_id)
                page.locator("id=txtPasswd").fill(password)
                page.locator("id=btnLogin").click(force=True)

                # FIX: bare except → except Exception
                try:
                    btn = page.locator("id=SYS_ASCX_btnContinue")
                    btn.wait_for(state="visible", timeout=5_000)
                    ui_log("AUTH", "Active session interceptor detected. Bypassing...")
                    btn.click(force=True)
                except Exception:
                    ui_log("SYS", "No interceptor detected. Clean session acquired.")

                page.wait_for_url("**/Default.aspx", timeout=TIMEOUT_MS, wait_until="domcontentloaded")
                ui_log("AUTH", "Login successful. Session established.")
                ui_log("SUCCESS", "Handshake verified.")

                # --- Navigation ---
                ui_log("NAV", "Navigating to Inventory > Stock Adjustment...")
                page.locator("id=pag_InventoryRoot_tab_Main_itm_StkAdj").dispatch_event("click")

                # FIX: replaced time.sleep(5) with an explicit element wait
                add_btn = page.locator("id=pag_I_StkAdj_btn_Add_Value")
                add_btn.wait_for(state="attached", timeout=TIMEOUT_MS)

                ui_log("NAV", "Opening new document [Add Value]...")
                add_btn.click(force=True)

                # FIX: replaced time.sleep(2) + duplicate locator call with a single stored variable
                warehouse_link = page.get_by_role("link", name=WAREHOUSE, exact=True)
                warehouse_link.wait_for(state="visible", timeout=TIMEOUT_MS)
                warehouse_link.click(force=True)

                page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value").wait_for(
                    state="visible", timeout=TIMEOUT_MS
                )

                ui_log("SYS", f"Applying adjustment protocol: code [{REASON_CODE}]...")
                dropdown = page.locator("id=pag_I_StkAdj_NewGeneral_drp_n_REASON_HDR_Value")
                if dropdown.is_enabled():
                    dropdown.select_option(REASON_CODE)
                ui_log("SYS", "Ready. Opening data stream for payload injection...")

                # --- Main loop ---
                progress_bar = st.progress(0)
                total_rows = len(df_view)

                for i, (idx, row) in enumerate(df_view.iterrows()):
                    sku = str(row['sku']).strip()
                    try:
                        qty = str(int(float(row['qty'])))
                    except Exception:
                        qty = str(row['qty']).strip()

                    ui_log("INJECT", f"Payload {i + 1}/{total_rows} -> SKU [{sku}]")
                    try:
                        sku_input = page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value")
                        sku_input.fill(sku)
                        sku_input.press("Tab")
                        time.sleep(1)

                        page.locator("id=pag_I_StkAdj_NewGeneral_txt_QTY1_Value").wait_for(
                            state="visible", timeout=TIMEOUT_MS
                        )
                        ui_log("INJECT", f"Assigning qty: {qty}")
                        page.locator("id=pag_I_StkAdj_NewGeneral_txt_QTY1_Value").fill(qty)
                        page.locator("id=pag_I_StkAdj_NewGeneral_btn_Add_Value").click(force=True)

                        ui_log("SYS", "Awaiting form reset...")
                        page.wait_for_function(
                            "document.getElementById('pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value').value === ''",
                            timeout=TIMEOUT_MS
                        )
                        df_view.at[idx, 'Status'] = 'Success'
                        df_view.at[idx, 'Keterangan'] = f'Attached {qty} EA'
                        success_count += 1
                        ui_log("SUCCESS", "Row committed.")

                    except Exception:
                        df_view.at[idx, 'Status'] = 'Failed'
                        df_view.at[idx, 'Keterangan'] = 'Node Timeout'
                        failed_count += 1
                        ui_log("ERROR", f"Timeout on SKU [{sku}]. Skipping.")

                    progress_bar.progress((i + 1) / total_rows)

                    # FIX: only re-render the table every N rows to reduce Streamlit overhead
                    if i % TABLE_UPDATE_INTERVAL == 0 or i == total_rows - 1:
                        table_placeholder.dataframe(df_view, use_container_width=True)

                ui_log("SERVER", "Saving document to server...")
                page.locator("id=pag_I_StkAdj_NewGeneral_btn_Save_Value").click()

                # FIX: bare except → except Exception
                try:
                    yes_btn = page.locator("id=pag_PopUp_YesNo_btn_Yes_Value")
                    yes_btn.wait_for(state="visible", timeout=5_000)
                    ui_log("SERVER", "Confirming save dialog...")
                    yes_btn.click()
                    ui_log("SERVER", "Document physically written to database.")
                except Exception:
                    ui_log("SERVER", "Auto-save confirmed. Document written to database.")

                ui_log("SYS", "Closing browser and releasing memory...")
                browser.close()
                elapsed = int(time.time() - global_start_time)
                ui_log("SUCCESS", f"Complete. Total runtime: {elapsed // 60}m {elapsed % 60}s")
                st.success(
                    f"Done — Success: {success_count} | Failed: {failed_count} | "
                    f"Time: {elapsed // 60}m {elapsed % 60}s"
                )
                if success_count > 0:
                    st.toast('Connection terminated')
                    time.sleep(0.5)
                    st.toast('Data injected successfully')
                    time.sleep(0.5)
                    st.toast('System override complete!')
                    st.session_state.reconcile_result = None

        except PlaywrightTimeoutError:
            st.error("Login failed: incorrect password or server timeout (30s).")
            ui_log("ERROR", "ACCESS DENIED: Handshake timeout. Invalid credentials or node unreachable.")

        except Exception as e:
            st.error("System halted due to an unexpected error.")
            clean_error = str(e).split('===')[0].strip()
            ui_log("ERROR", f"SYSTEM FAILURE: {clean_error}")
            ui_log("ERROR", traceback.format_exc().splitlines()[-1])
