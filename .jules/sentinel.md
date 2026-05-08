## 2026-05-08 - Prevent XSS in Streamlit Markdown
**Vulnerability**: Unescaped dynamic variables interpolated into f-strings used inside `st.markdown(..., unsafe_allow_html=True)` allowed potential execution of malicious JavaScript (XSS).
**Learning**: Any use of `unsafe_allow_html=True` in Streamlit must be thoroughly audited. Variables sourced from user input, external data, or session state are not inherently safe and must be explicitly sanitized.
**Prevention**: Always import `html` and wrap interpolated variables with `html.escape()` before injecting them into HTML payloads rendered by Streamlit.
