## 2026-05-08 - [Streamlit unsafe_allow_html Injection]
**Vulnerability:** User inputs (like usernames, system error messages, distributor names) were interpolated directly into `st.markdown(..., unsafe_allow_html=True)` and Telegram bot messages with `parse_mode="HTML"` without HTML escaping.
**Learning:** In Streamlit, `unsafe_allow_html=True` acts identically to standard HTML injection (XSS). Any dynamic variable passed into such a string must be sanitized, otherwise it exposes the application to client-side attacks or application crash (Telegram API rejects invalid HTML tags).
**Prevention:** Always wrap dynamic variables in `html.escape()` before interpolating them into HTML strings that will be rendered or parsed as HTML.
