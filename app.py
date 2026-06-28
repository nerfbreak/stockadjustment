import streamlit as st

st.set_page_config(page_title="Redirecting...", page_icon="🔗")

st.markdown(
    """
    <meta http-equiv="refresh" content="0; url=https://newspage.streamlit.app" />
    <div style="text-align: center; margin-top: 100px; font-family: sans-serif;">
        <h2>Aplikasi Telah Pindah! / App Has Moved!</h2>
        <p>Anda akan diarahkan ke alamat yang baru secara otomatis.</p>
        <p>Jika tidak diarahkan, silakan klik tautan di bawah ini:</p>
        <br>
        <a href="https://newspage.streamlit.app" style="padding: 10px 20px; background-color: #FF4B4B; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
            Menuju newspage.streamlit.app
        </a>
    </div>
    """,
    unsafe_allow_html=True
)
