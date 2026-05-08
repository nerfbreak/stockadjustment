import bcrypt
import streamlit as st
import database
import os
import re

def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def load_secrets():
    """Simple manual parser for .streamlit/secrets.toml if running outside of streamlit."""
    secrets_path = ".streamlit/secrets.toml"
    if os.path.exists(secrets_path):
        with open(secrets_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                st.secrets[key] = val
        return True
    return False

def migrate_passwords():
    """
    Fetches all users from users_auth, hashes their plaintext passwords,
    and updates the records in Supabase.
    """
    if not st.secrets:
        load_secrets()

    supabase = database.init_supabase()
    if not supabase:
        print("Error: Could not initialize Supabase client. Check your .streamlit/secrets.toml")
        return

    try:
        # Fetch all users
        res = supabase.table("users_auth").select("username, password").execute()
        users = res.data

        if not users:
            print("No users found in users_auth table.")
            return

        print(f"Found {len(users)} users. Starting migration...")

        for user in users:
            username = user['username']
            plaintext_password = user['password']

            if not plaintext_password:
                print(f"Skipping user '{username}': Empty password.")
                continue

            # Check if it's already hashed (bcrypt hashes start with $2b$ or $2a$)
            if plaintext_password.startswith('$2b$') or plaintext_password.startswith('$2a$'):
                print(f"Skipping user '{username}': Password already hashed.")
                continue

            # Hash the password
            hashed_password = hash_password(plaintext_password)

            # Update the user record
            supabase.table("users_auth").update({"password": hashed_password}).eq("username", username).execute()
            print(f"Successfully migrated user '{username}'.")

        print("Migration complete!")

    except Exception as e:
        print(f"An error occurred during migration: {e}")

if __name__ == "__main__":
    migrate_passwords()
