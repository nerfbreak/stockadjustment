## 2024-05-08 - Streamlit Unsafe HTML Rendering XSS

**Vulnerability**
Streamlit applications frequently use `st.markdown(..., unsafe_allow_html=True)` to render custom HTML blocks or UI elements. When dynamic user input or database variables (such as user accounts or API tokens) are injected into these formatted strings without proper sanitization, it exposes the application to Cross-Site Scripting (XSS).

**Learning**
Python's built-in `html.escape()` is an essential tool to neutralize HTML-specific characters (`<`, `>`, `&`, `"`, `'`) before interpolation. Using it prevents the browser from interpreting potentially malicious injected inputs as executable code.

**Prevention**
Whenever using `unsafe_allow_html=True` with Python f-strings or format methods, rigorously enforce that any dynamic or non-hardcoded variable is passed through `html.escape()` or an equivalent safe rendering mechanism. Avoid placing unvalidated input directly into DOM structures.
