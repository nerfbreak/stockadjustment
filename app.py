import streamlit as st

st.set_page_config(page_title="App Moved", page_icon="🚀", layout="centered")

# Hide standard Streamlit header/footer for cleaner UI
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

html_content = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');

/* Center everything in the main container */
.move-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 70vh;
    font-family: 'Inter', sans-serif;
    color: #ffffff;
    text-align: center;
    animation: fadeIn 1s ease-in-out;
}

/* Beautiful dark card styling */
.card {
    background: linear-gradient(145deg, #1e1e1e, #2d2d2d);
    padding: 3rem 4rem;
    border-radius: 20px;
    box-shadow: 0 20px 40px rgba(0,0,0,0.4);
    border: 1px solid #3d3d3d;
    max-width: 600px;
    width: 100%;
}

.icon {
    font-size: 4rem;
    margin-bottom: 1rem;
    animation: float 3s ease-in-out infinite;
}

/* Gradient text for the heading */
h1 {
    font-size: 2.5rem;
    font-weight: 800;
    margin-bottom: 1rem;
    background: -webkit-linear-gradient(45deg, #FF4B4B, #FF8F8F);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    padding-bottom: 10px;
}

p {
    font-size: 1.1rem;
    color: #a0aec0;
    margin-bottom: 2.5rem;
    line-height: 1.6;
}

/* Stylish animated button */
.btn {
    display: inline-block;
    padding: 1rem 2.5rem;
    font-size: 1.1rem;
    font-weight: 600;
    color: #ffffff !important;
    background: linear-gradient(90deg, #FF4B4B 0%, #ff6b6b 100%);
    text-decoration: none;
    border-radius: 50px;
    transition: all 0.3s ease;
    box-shadow: 0 10px 20px rgba(255, 75, 75, 0.3);
}

.btn:hover {
    transform: translateY(-3px);
    box-shadow: 0 15px 25px rgba(255, 75, 75, 0.5);
    background: linear-gradient(90deg, #ff6b6b 0%, #FF4B4B 100%);
}

/* Subtle animations */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes float {
    0% { transform: translateY(0px); }
    50% { transform: translateY(-10px); }
    100% { transform: translateY(0px); }
}
</style>

<div class="move-container">
    <div class="card">
        <div class="icon">🚀</div>
        <h1>We've Moved!</h1>
        <p>Aplikasi Stock Adjustment telah dipindahkan ke server baru untuk performa dan pengalaman yang lebih baik. Silakan klik tombol di bawah ini untuk menuju ke aplikasi yang baru.</p>
        <a href="https://newspage.streamlit.app" class="btn" target="_blank" rel="noopener noreferrer">Buka Aplikasi Baru</a>
    </div>
</div>
"""

st.markdown(html_content, unsafe_allow_html=True)
