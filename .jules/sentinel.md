## 2026-05-08 - Prevent XSS in Streamlit Markdown
**Vulnerability**: Unescaped dynamic variables interpolated into f-strings used inside `st.markdown(..., unsafe_allow_html=True)` allowed potential execution of malicious JavaScript (XSS).
**Learning**: Any use of `unsafe_allow_html=True` in Streamlit must be thoroughly audited. Variables sourced from user input, external data, or session state are not inherently safe and must be explicitly sanitized.
**Prevention**: Always import `html` and wrap interpolated variables with `html.escape()` before injecting them into HTML payloads rendered by Streamlit.
## 2026-05-08 - [Streamlit XSS Fix]\n**Vulnerability:** Cross-Site Scripting (XSS) via Unsafe HTML in Streamlit due to interpolating unescaped session variables into markdown with `unsafe_allow_html=True`.\n**Learning:** When using Streamlit's `st.markdown(..., unsafe_allow_html=True)`, any dynamic variables must be escaped using `html.escape()`.\n**Prevention:** Always escape user-controlled or session-stored strings before embedding them in HTML payloads.

## 2026-05-08 - [🔒 Fix plaintext password storage]
**Vulnerability**: The authentication logic in `database.py` retrieved users by comparing plaintext passwords directly in the database query. This exposes credentials if the database is compromised.
**Learning**: Replaced plaintext authentication with a robust key derivation function (`bcrypt`). Since the app lacks in-band registration flows, the fix involved fetching the stored hashed password by username and verifying it using `bcrypt.checkpw()`. It is also important to ensure compiled files (`__pycache__`) are not checked into version control during development.
**Prevention**: Always use a secure, salted hash function (e.g., `bcrypt`, `Argon2`) for password storage and verification. Never store or compare passwords in plaintext. Ensure `.gitignore` correctly handles `__pycache__/` and `*.pyc` files.
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
