import time
import streamlit as st
from supabase import create_client

@st.cache_data(ttl=600)
def get_distributor_list_optimized(_supabase):
    time.sleep(1) # simulate query
    return ["A", "B", "C"]

def get_distributor_list_original(supabase):
    time.sleep(1) # simulate query
    return ["A", "B", "C"]

class MockSupabase:
    def __init__(self):
        pass

def benchmark():
    sb = MockSupabase()

    t0 = time.time()
    get_distributor_list_original(sb)
    get_distributor_list_original(sb)
    t_orig = time.time() - t0

    t0 = time.time()
    get_distributor_list_optimized(sb)
    get_distributor_list_optimized(sb)
    t_opt = time.time() - t0

    print(f"Original: {t_orig:.4f}s")
    print(f"Optimized: {t_opt:.4f}s")

if __name__ == "__main__":
    benchmark()
