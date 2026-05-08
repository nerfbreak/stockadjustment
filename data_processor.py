import pandas as pd
import zipfile
import streamlit as st

def load_data(file):
    if file is None: return None
    df = None
    filename = file.name.lower()
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file, sep='\t', dtype=str)
            if df.shape[1] <= 1:
                file.seek(0)
                df = pd.read_csv(file, sep=',', dtype=str)
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file, dtype=str)
        elif filename.endswith('.zip'):
            with zipfile.ZipFile(file) as z:
                target = next((n for n in z.namelist() if "INVT_MASTER" in n and n.lower().endswith(".csv")), None)
                if not target: target = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
                if target:
                    with z.open(target) as f:
                        df = pd.read_csv(f, sep='\t', dtype=str)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None
    return df

def process_compare(df1, df2, sku_col1, desc_col1, qty_col1, sku_col2, qty_col2, TARGET_SKUS, multipliers):
    d1 = df1[[sku_col1, desc_col1, qty_col1]].copy()
    d1 = d1.dropna(subset=[sku_col1])
    d1[sku_col1] = d1[sku_col1].astype(str).str.split('.').str[0].str.strip()
    d1 = d1[~d1[sku_col1].str.lower().isin(['nan', 'none', '', 'total', 'grand total'])]
    
    target_skus_set = set(TARGET_SKUS)
    mask1 = d1[sku_col1].astype(str).isin(target_skus_set)
    d1.loc[mask1, sku_col1] = '0' + d1.loc[mask1, sku_col1].astype(str)
    d1[qty_col1] = pd.to_numeric(d1[qty_col1], errors='coerce').fillna(0)
    d1_agg = (d1.groupby(sku_col1).agg({desc_col1: 'first', qty_col1: 'sum'}).reset_index().rename(columns={sku_col1: 'SKU', desc_col1: 'Description', qty_col1: 'Newspage'}))
    
    if 'Aktif' in df2.columns: 
        df2 = df2[pd.to_numeric(df2['Aktif'], errors='coerce') == 1]
    if 'Nama Gudang' in df2.columns: 
        df2 = df2[df2['Nama Gudang'].astype(str).str.strip().str.upper() == 'GUDANG UTAMA']
        
    d2 = df2[[sku_col2, qty_col2]].copy()
    d2 = d2.dropna(subset=[sku_col2])
    d2[sku_col2] = d2[sku_col2].astype(str).str.split('.').str[0].str.strip()
    d2 = d2[~d2[sku_col2].str.lower().isin(['nan', 'none', '', 'total', 'grand total'])]
    
    mask2 = d2[sku_col2].astype(str).isin(target_skus_set)
    d2.loc[mask2, sku_col2] = '0' + d2.loc[mask2, sku_col2].astype(str)
    d2[qty_col2] = pd.to_numeric(d2[qty_col2], errors='coerce').fillna(0)
    
    if multipliers:
        mult_map = {rule['sku_target']: rule['multiplier_value'] for rule in multipliers}
        d2[qty_col2] *= d2[sku_col2].map(mult_map).fillna(1.0)

    d2_agg = (d2.groupby(sku_col2)[qty_col2].sum().reset_index().rename(columns={sku_col2: 'SKU', qty_col2: 'Distributor'}))
    
    merged = pd.merge(d1_agg, d2_agg, on='SKU', how='outer')
    merged[['Newspage', 'Distributor']] = merged[['Newspage', 'Distributor']].fillna(0)
    merged['Description'] = merged['Description'].fillna('ITEM NOT IN MASTER')
    merged['Selisih'] = merged['Distributor'] - merged['Newspage']
    merged['Status'] = 'Mismatch'
    merged.loc[merged['Selisih'] == 0, 'Status'] = 'Match'
    
    mismatches = merged[merged['Status'] == 'Mismatch'].sort_values('Selisih')
    return merged, mismatches
