
import streamlit as st
from supabase import create_client, Client
from cryptography.fernet import Fernet
import os

def get_cipher():
    key = st.secrets.get("ENCRYPTION_KEY", "")
    if not key:
        return None
    try:
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)
    except:
        return None

def decrypt_password(encrypted_str):
    if not encrypted_str: return ""
    try:
        cipher = get_cipher()
        if cipher:
            return cipher.decrypt(encrypted_str.encode()).decode()
        return encrypted_str
    except Exception:
        # Backward compatibility: if it cannot be decrypted, assume it's plaintext
        return encrypted_str


@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    if url and key:
        return create_client(url, key)
    return None

def get_system_config(supabase):
    reason_code = "SA2"
    warehouse = "GOOD_WHS"
    if supabase:
        try:
            res_config = supabase.table("system_config").select("*").execute()
            for cfg in res_config.data:
                if cfg['config_key'] == 'REASON_CODE': reason_code = cfg['config_value']
                if cfg['config_key'] == 'WAREHOUSE': warehouse = cfg['config_value']
        except: pass
    return reason_code, warehouse

def authenticate_user(supabase, username, password):
    if supabase:
        try:
            res_user = supabase.table("users_auth").select("*").eq("username", username).eq("password", password).execute()
            if res_user.data:
                return True
        except: pass
    return False

def get_distributor_list(supabase):
    list_dist = []
    if supabase:
        try:
            res = supabase.table("distributor_vault").select("nama_distributor").execute()
            list_dist = [d['nama_distributor'] for d in res.data]
        except: pass
    if not list_dist: list_dist = ["Belum ada data di Database"]
    return list_dist

def get_distributor_creds(supabase, selected_distributor):
    bot_user, bot_pass = "", ""
    if supabase:
        try:
            res = supabase.table("distributor_vault").select("np_user_id, np_password").eq("nama_distributor", selected_distributor).execute()
            if res.data:
                bot_user = res.data[0]['np_user_id']
                bot_pass = decrypt_password(res.data[0]['np_password'])
        except: pass
    return bot_user, bot_pass

def get_target_skus(supabase):
    TARGET_SKUS = []
    if supabase:
        try:
            res_sku = supabase.table("sku_formatting_rules").select("sku_code").execute()
            TARGET_SKUS = [s['sku_code'] for s in res_sku.data]
        except: pass
    if not TARGET_SKUS: 
        TARGET_SKUS = ['373103', '373104', '373105', '373106', '373108', '373110', '373112', '135428', '137118', '137120', '167209', '172130', '172131', '205901', '22583', '22595', '260656', '260659', '304095', '304100', '304102', '304157', '304161', '304164', '323044', '372264', '373100']
    return TARGET_SKUS

def get_multiplier_rules(supabase, current_np_user_id):
    rules = []
    if supabase and current_np_user_id:
        try:
            res_mult = supabase.table("distributor_sku_multiplier").select("sku_target, multiplier_value").eq("np_user_id", current_np_user_id).execute()
            if res_mult.data:
                rules = res_mult.data
        except: pass
    return rules

def log_extraction_history(supabase, selected_distributor, current_user):
    if supabase:
        try:
            supabase.table("extraction_history").insert({
                "distributor_name": selected_distributor,
                "extracted_by": current_user,
                "status": "Success"
            }).execute()
        except: pass

def log_adjustment(supabase, sku, qty, status, keterangan, bot_user):
    if supabase:
        try:
            # Cegah error integer kalau timeout dan node kosong
            safe_qty = int(qty) if str(qty).replace('-','').isdigit() else 0
            supabase.table("adjustment_logs").insert({
                "sku": sku, "qty": safe_qty, "status": status, 
                "keterangan": keterangan, "np_user": bot_user
            }).execute()
        except: pass
