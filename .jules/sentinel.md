
## 2026-05-08 - [🔒 Fix plaintext password storage]
**Vulnerability**: The authentication logic in `database.py` retrieved users by comparing plaintext passwords directly in the database query. This exposes credentials if the database is compromised.
**Learning**: Replaced plaintext authentication with a robust key derivation function (`bcrypt`). Since the app lacks in-band registration flows, the fix involved fetching the stored hashed password by username and verifying it using `bcrypt.checkpw()`. It is also important to ensure compiled files (`__pycache__`) are not checked into version control during development.
**Prevention**: Always use a secure, salted hash function (e.g., `bcrypt`, `Argon2`) for password storage and verification. Never store or compare passwords in plaintext. Ensure `.gitignore` correctly handles `__pycache__/` and `*.pyc` files.
