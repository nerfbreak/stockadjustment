import streamlit as st
from supabase import create_client, Client
import bcrypt

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
        except Exception: pass
    return reason_code, warehouse

def authenticate_user(supabase, username, password):
    if supabase:
        try:
            res_user = supabase.table("users_auth").select("*").eq("username", username).execute()
            if res_user.data:
                stored_hash = res_user.data[0].get('password', '')
                if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
                    return True
        except: pass
                return True
        except Exception: pass
    return False

def get_distributor_list(supabase):
    list_dist = []
    if supabase:
        try:
            res = supabase.table("distributor_vault").select("nama_distributor").execute()
            list_dist = [d['nama_distributor'] for d in res.data]
        except Exception: pass
    if not list_dist: list_dist = ["Belum ada data di Database"]
    return list_dist

def get_distributor_creds(supabase, selected_distributor):
    bot_user, bot_pass = "", ""
    if supabase:
        try:
            res = supabase.table("distributor_vault").select("np_user_id, np_password").eq("nama_distributor", selected_distributor).execute()
            if res.data:
                bot_user = res.data[0]['np_user_id']
                bot_pass = res.data[0]['np_password']
        except Exception: pass
    return bot_user, bot_pass

@st.cache_data(ttl=3600)
def get_target_skus(_supabase):
    TARGET_SKUS = []
    if _supabase:
        try:
            res_sku = _supabase.table("sku_formatting_rules").select("sku_code").execute()
            TARGET_SKUS = [s['sku_code'] for s in res_sku.data]
        except Exception: pass
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
        except Exception: pass
    return rules

def log_extraction_history(supabase, selected_distributor, current_user):
    if supabase:
        try:
            supabase.table("extraction_history").insert({
                "distributor_name": selected_distributor,
                "extracted_by": current_user,
                "status": "Success"
            }).execute()
        except Exception: pass

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

def log_adjustments_bulk(supabase, adjustments_list):
    """
    Perform a bulk insert of multiple adjustment logs.
    adjustments_list should be a list of dicts:
    [{'sku': ..., 'qty': ..., 'status': ..., 'keterangan': ..., 'np_user': ...}, ...]
    """
    if supabase and adjustments_list:
        try:
            data_to_insert = []
            for item in adjustments_list:
                qty = item.get('qty', 0)
                safe_qty = int(qty) if str(qty).replace('-','').isdigit() else 0
                data_to_insert.append({
                    "sku": item.get('sku'),
                    "qty": safe_qty,
                    "status": item.get('status'),
                    "keterangan": item.get('keterangan'),
                    "np_user": item.get('np_user')
                })

            # Chunk the inserts to avoid payload size limits if list is very large
            # Streamlit/Supabase postgrest limit is generous but good practice
            chunk_size = 1000
            for i in range(0, len(data_to_insert), chunk_size):
                chunk = data_to_insert[i:i + chunk_size]
                supabase.table("adjustment_logs").insert(chunk).execute()
        except Exception as e:
            # Silently fail as the original function does
            pass
        except Exception: pass
