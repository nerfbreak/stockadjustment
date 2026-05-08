## 2024-05-08 - Streamlit Unsafe HTML Rendering XSS

**Vulnerability**
Streamlit applications frequently use `st.markdown(..., unsafe_allow_html=True)` to render custom HTML blocks or UI elements. When dynamic user input or database variables (such as user accounts or API tokens) are injected into these formatted strings without proper sanitization, it exposes the application to Cross-Site Scripting (XSS).

**Learning**
Python's built-in `html.escape()` is an essential tool to neutralize HTML-specific characters (`<`, `>`, `&`, `"`, `'`) before interpolation. Using it prevents the browser from interpreting potentially malicious injected inputs as executable code.

**Prevention**
Whenever using `unsafe_allow_html=True` with Python f-strings or format methods, rigorously enforce that any dynamic or non-hardcoded variable is passed through `html.escape()` or an equivalent safe rendering mechanism. Avoid placing unvalidated input directly into DOM structures.
## 2026-05-08 - XSS via Unsafe HTML in Streamlit\n\n**Vulnerability**\nStreamlit components rendered with `unsafe_allow_html=True` are vulnerable to XSS if they interpolate unsanitized user input or state variables.\n\n**Learning**\nEven internal state variables like `st.session_state.current_user` or database values should be treated as untrusted and explicitly escaped if injected directly into HTML strings, as opposed to using native Streamlit text components which handle escaping automatically.\n\n**Prevention**\nAlways use `html.escape(str(variable))` to sanitize any dynamic input before interpolating it into formatted strings that will be rendered as HTML, or when sending HTML-formatted Telegram messages.\n
## 2026-05-08 - [Streamlit unsafe_allow_html Injection]
**Vulnerability:** User inputs (like usernames, system error messages, distributor names) were interpolated directly into `st.markdown(..., unsafe_allow_html=True)` and Telegram bot messages with `parse_mode="HTML"` without HTML escaping.
**Learning:** In Streamlit, `unsafe_allow_html=True` acts identically to standard HTML injection (XSS). Any dynamic variable passed into such a string must be sanitized, otherwise it exposes the application to client-side attacks or application crash (Telegram API rejects invalid HTML tags).
**Prevention:** Always wrap dynamic variables in `html.escape()` before interpolating them into HTML strings that will be rendered or parsed as HTML.
