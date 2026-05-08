import streamlit as st
import time
import requests
import database
import data_processor
import playwright_engine
import html

# --- 1. CONFIG & UI HELPERS ---
st.set_page_config(page_title="Stock Adjustment Newspage", layout="wide")

# Fungsi Footer Copyright
def render_footer():
    st.markdown("""
    <div style='text-align: center; margin-top: 20px; margin-bottom: 10px;'>
        <span style='font-family: "Inter", sans-serif; font-size: 0.6rem; color: #64748b; letter-spacing: 0.05em; text-transform: uppercase;'>
            &copy; 2026 IT Support Newspage. by kopi mang toni.
        </span>
    </div>
    """, unsafe_allow_html=True)

# Inisialisasi Session State agar tidak Error AttributeError
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "current_user" not in st.session_state: st.session_state.current_user = "Guest"

# --- 2. AUTHENTICATION GATEKEEPER ---
if not st.session_state.logged_in:
    # CSS SAKTI: NO SCROLL, FULL CENTER, LEFT-ALIGNED INPUT
    st.markdown("""
        <style>
        /* Matikan scroll dan paksa full screen */
        html, body, [data-testid="stAppViewContainer"], [data-testid="stMainViewContainer"] {
            overflow: hidden !important;
            height: 100vh !important;
            width: 100vw !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        /* Sembunyikan Header Streamlit */
        [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] {
            display: none !important;
        }

        /* Centering Kontainer Utama */
        .main .block-container {
            height: 100vh !important;
            max-width: 100vw !important;
            padding: 0 !important;
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
        }

        /* Card Login Minimalis */
        div[data-testid="stForm"] {
            border: 1px solid #334155 !important;
            border-radius: 16px !important;
            background-color: #0f172a !important;
            padding: 40px !important;
            width: 380px !important;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5) !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }

        /* Label Center */
        div[data-testid="stTextInput"] label p {
            font-family: "Inter", sans-serif !important;
            font-size: 0.7rem !important;
            font-weight: 700 !important;
            color: #94a3b8 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.1em !important;
            text-align: center !important;
            width: 100% !important;
        }

        /* Input Field Rata Kiri */
        div[data-testid="stTextInput"] input {
            background-color: #1e293b !important;
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
            color: #f8fafc !important;
            text-align: left !important;
            padding-left: 15px !important;
        }

        div[data-testid="InputInstructions"] { display: none !important; }
        </style>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("Username", placeholder="")
        password = st.text_input("Password", type="password", placeholder="")
        st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
        submit = st.form_submit_button("LOGIN", use_container_width=True)
        
        if submit:
            supabase = database.init_supabase()
            if database.authenticate_user(supabase, username, password):
                st.session_state.logged_in = True
                st.session_state.current_user = username
                st.rerun()
            else:
                st.markdown("<p style='color: #ef4444; font-size: 0.8rem; text-align: center; margin-top: 10px;'>Invalid credentials.</p>", unsafe_allow_html=True)

    render_footer()
    st.stop()

# --- 3. DASHBOARD UTAMA (SETELAH LOGIN) ---
# CSS GLOBAL UNTUK HALAMAN UTAMA
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono&display=swap');
    
    /* Bikin Judul & Label Center di Dashboard */
    div[data-testid="stSelectbox"] label p, 
    div[data-testid="stTextInput"] label p,
    div[data-testid="stFileUploader"] label p {
        font-family: "Inter", sans-serif !important;
        font-size: 0.75rem !important;
        font-weight: 700 !important;
        color: #94a3b8 !important;
        text-transform: uppercase !important;
        text-align: center !important;
        width: 100% !important;
    }
    
    /* Style Button Browse Files */
    div[data-testid="stFileUploader"] button {
        background-color: #1e293b !important;
        color: #3b82f6 !important;
        border: 1px solid #334155 !important;
        border-radius: 6px !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 4. MAIN UI LAYOUT ---
st.markdown("<div class='live-indicator'>LIVE</div>", unsafe_allow_html=True)
st.markdown("<h1>Compare & Adjustment Stock</h1>", unsafe_allow_html=True)

# Menampilkan User dengan aman agar tidak crash
user_now = html.escape(st.session_state.get('current_user', 'Guest'))

st.markdown(f"""
    <div style='display: inline-block; margin-top: -4px; margin-bottom: 20px;'>
        <span style='font-family: "Inter", sans-serif; font-size: 0.65rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.1em; margin-right: 8px;'>Active Session</span>
        <span style='font-family: "Inter", sans-serif; font-size: 0.65rem; font-weight: 700; color: #3b82f6; text-transform: uppercase; letter-spacing: 0.1em;'>{user_now}</span>
    </div>
""", unsafe_allow_html=True)

st.markdown("---")

# ... Sisa kodingan logika bot lu lanjut di bawah sini ...
st.write("Aplikasi Berjalan...")

render_footer()
