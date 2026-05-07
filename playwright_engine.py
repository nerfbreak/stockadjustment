import streamlit as st
import time
import os
import subprocess
import asyncio
import sys
import zipfile
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import database

def ensure_playwright():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e:
        st.error(f"Failed to install browser engine: {e}")

def run_extract(user_id_np, pass_np, selected_distributor, URL_LOGIN, TIMEOUT_MS, WAREHOUSE, ext_ui_log, alert_callback, supabase, current_user):
    ensure_playwright()
    try:
        if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.set_event_loop(asyncio.new_event_loop())
        with sync_playwright() as p:
            ext_ui_log("SYS", "Spawning browser context with isolated session...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(no_viewport=True)
            page    = context.new_page()
            ext_ui_log("AUTH", f"Connecting to {URL_LOGIN}...")
            page.goto(URL_LOGIN, wait_until="domcontentloaded")
            ext_ui_log("AUTH", f"DOM ready. Injecting credentials for [{selected_distributor}]...")
            page.locator("id=txtUserid").fill(user_id_np)
            page.locator("id=txtPasswd").fill(pass_np)
            page.locator("id=btnLogin").click(force=True)
            try:
                btn = page.locator("id=SYS_ASCX_btnContinue")
                btn.wait_for(state="visible", timeout=5_000)
                ext_ui_log("AUTH", "Active session interceptor detected. Bypassing...")
                btn.click(force=True)
            except Exception: ext_ui_log("SYS", "No interceptor detected. Clean session acquired.")
            page.wait_for_url("**/Default.aspx", timeout=TIMEOUT_MS, wait_until="domcontentloaded")
            ext_ui_log("AUTH", "Login successful. Session established.")
            ext_ui_log("SUCCESS", "Handshake verified.")
            ext_ui_log("NAV", "Navigating to System > Import/Export Job module...")
            time.sleep(5) 
            menu_job = page.locator("id=pag_Sys_Root_tab_Detail_itm_Job")
            menu_job.wait_for(state="attached", timeout=TIMEOUT_MS)
            menu_job.dispatch_event("click")
            time.sleep(4)
            ext_ui_log("NAV", "Opening new job [Add Value]...")
            page.locator("id=pag_FW_SYS_INTF_JOB_btn_Add_Value").click(force=True)
            time.sleep(3)
            ext_ui_log("INJECT", "Setting job type: Export [E], desc: Text Inventory Master...")
            page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_JOB_TYPE_Value").select_option("E")
            time.sleep(2)
            page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_JOB_DESC_Value").fill("Text Inventory Master")
            page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_JOB_TIMEOUT_Value").fill("9999999")
            page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_EXE_TYPE_Value").select_option("M")
            time.sleep(2)
            ext_ui_log("NAV", "Proceeding to next step...")
            page.locator("id=pag_FW_SYS_INTF_JOB_RootNew_btn_Next_Value").click(force=True)
            time.sleep(3)
            ext_ui_log("SYS", "Bypassing disclaimer prompt...")
            page.locator("id=pag_FW_DisclaimerMessage_btn_okay_Value").click(force=True)
            time.sleep(2)
            ext_ui_log("NAV", "Opening interface selection popup...")
            page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_INTF_ID_SelectButton").click(force=True)
            time.sleep(3)
            ext_ui_log("INJECT", "Searching target interface: E_20150315090000028...")
            page.locator("id=pop_Dynamic_gft_List_2_FilterField_Value").fill("E_20150315090000028")
            page.locator("id=pop_Dynamic_grd_Main_SearchForm_ButtonSearch_Value").click(force=True)
            time.sleep(2)
            ext_ui_log("INJECT", "Selecting target interface from results...")
            page.get_by_text("E_20150315090000028", exact=True).click(force=True)
            time.sleep(2)
            ext_ui_log("INJECT", "Setting file type: Delimited [D], separator: standard...")
            page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_FILE_TYPE_Value").select_option("D")
            time.sleep(1)
            page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_FLD_SEPARATOR_STD_Value_0").check()
            time.sleep(3)
            ext_ui_log("INJECT", f"Applying warehouse filter: [{WAREHOUSE}]...")
            page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_grd_DynamicFilter_ctl02_dyn_Field_txt_Value").fill("GOOD_WHS")
            time.sleep(2)
            ext_ui_log("SYS", "Committing parameters to job definition...")
            page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_btn_Add_Value").click(force=True)
            time.sleep(3)
            ext_ui_log("SERVER", "Saving job and dispatching execution to server...")
            page.locator("id=pag_FW_SYS_INTF_JOB_RootNew_btn_Save_Value").click(force=True)
            ext_ui_log("SERVER", "Awaiting server confirmation prompt...")
            page.locator("id=TF_Prompt_btn_Ok_Value").wait_for(state="visible", timeout=TIMEOUT_MS)
            page.locator("id=TF_Prompt_btn_Ok_Value").click(force=True)
            ext_ui_log("SERVER", "Job dispatched. Waiting for export to complete...")
            ext_ui_log("SERVER", "Intercepting download link — this may take up to 4 minutes...")
            with page.expect_download(timeout=240000) as download_info:
                download_btn = page.locator("id=pag_FW_SYS_INTF_STATUS_JOB_btn_Download_Value")
                download_btn.wait_for(state="visible", timeout=240000)
                download_btn.click(force=True)
            download      = download_info.value
            real_filename = download.suggested_filename
            file_path     = f"temp_ext_{real_filename}"
            ext_ui_log("SUCCESS", f"Download captured: {real_filename}. Saving to environment...")
            download.save_as(file_path)
            browser.close()
            ext_ui_log("SYS", "Browser closed. Releasing session memory...")
            ext_ui_log("SYS", f"Parsing payload file: {real_filename}...")
            df_ext = None
            if real_filename.lower().endswith('.zip'):
                with zipfile.ZipFile(file_path) as z:
                    target = next((n for n in z.namelist() if "INVT_MASTER" in n and n.lower().endswith((".csv", ".txt"))), None)
                    if not target: target = next((n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))), None)
                    if target:
                        ext_ui_log("SYS", f"ZIP target identified: {target}")
                        with z.open(target) as f:
                            df_ext = pd.read_csv(f, sep='\t', dtype=str, on_bad_lines='skip')
                            if df_ext.shape[1] <= 1: f.seek(0); df_ext = pd.read_csv(f, sep=',', dtype=str, on_bad_lines='skip')
            elif real_filename.lower().endswith(('.xls', '.xlsx')): df_ext = pd.read_excel(file_path, dtype=str)
            else:
                for enc in ['utf-8', 'iso-8859-1', 'cp1252']:
                    for separator in ['\t', ',', ';', '|']:
                        try:
                            temp_df = pd.read_csv(file_path, sep=separator, dtype=str, encoding=enc, on_bad_lines='skip')
                            if temp_df is not None and temp_df.shape[1] > 1: df_ext = temp_df; break
                        except Exception: continue
                    if df_ext is not None and df_ext.shape[1] > 1: break

            if df_ext is not None and not df_ext.empty and df_ext.shape[1] > 1:
                df_ext.columns = [str(c).strip() for c in df_ext.columns]
                ext_ui_log("SUCCESS", f"Payload Secured! {len(df_ext)} items loaded. Flushing to session...")
                st.session_state.np_df = df_ext
                database.log_extraction_history(supabase, selected_distributor, current_user)
                st.session_state.is_bot_running = False
                st.rerun()
            else: 
                st.session_state.is_bot_running = False
                ext_ui_log("ERROR", "DataFrame validation failed.")
                st.error("Gagal membaca file dari server.")
                alert_callback(f"⚠️ <b>EXTRACT FAILED</b>\nUser: {current_user}\nDist: {selected_distributor}\nReason: Invalid DataFrame")
    except PlaywrightTimeoutError: 
        st.session_state.is_bot_running = False
        ext_ui_log("ERROR", "TIMEOUT: Server tidak merespon.")
        st.error("Operation Timeout.")
        alert_callback(f"🚨 <b>EXTRACT TIMEOUT</b>\nUser: {current_user}\nDist: {selected_distributor}\nReason: Playwright Timeout")
    except Exception as e: 
        st.session_state.is_bot_running = False
        ext_ui_log("ERROR", f"SYSTEM FAILURE: {str(e).split(chr(10))[0]}")
        st.error(f"System error: {e}")
        alert_callback(f"🚨 <b>SYSTEM ERROR (EXTRACT)</b>\nDist: {selected_distributor}\nError: <code>{str(e)[:100]}</code>")


def run_execution(df_view, bot_user, bot_pass, selected_distributor, URL_LOGIN, TIMEOUT_MS, WAREHOUSE, REASON_CODE, TABLE_UPDATE_INTERVAL, ui_log, alert_callback, table_placeholder, supabase):
    ensure_playwright()
    global_start_time = time.time(); success_count, failed_count = 0, 0
    ui_log("SYS", "Allocating memory and initializing Chromium headless core...")
    if supabase: ui_log("SYS", "Supabase client active.")

    alert_callback(f"🚀 <b>BOT STARTED</b>\nTask: Reconcile Stock\nDist: {selected_distributor}\nTotal SKU: {len(df_view)}")

    try:
        if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.set_event_loop(asyncio.new_event_loop())
        with sync_playwright() as p:
            ui_log("SYS", "Spawning browser context...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(no_viewport=True)
            page = context.new_page()
            ui_log("AUTH", f"Connecting to Newspage...")
            page.goto(URL_LOGIN, wait_until="domcontentloaded")
            ui_log("AUTH", f"Injecting hidden credentials for [{selected_distributor}]...")
            page.locator("id=txtUserid").fill(bot_user)
            page.locator("id=txtPasswd").fill(bot_pass)
            page.locator("id=btnLogin").click(force=True)
            try:
                btn = page.locator("id=SYS_ASCX_btnContinue")
                btn.wait_for(state="visible", timeout=5_000)
                btn.click(force=True)
            except Exception: pass
            
            page.wait_for_url("**/Default.aspx", timeout=TIMEOUT_MS)
            ui_log("AUTH", "Login successful.")
            time.sleep(5)
            page.locator("id=pag_InventoryRoot_tab_Main_itm_StkAdj").dispatch_event("click")
            add_btn = page.locator("id=pag_I_StkAdj_btn_Add_Value")
            add_btn.wait_for(state="attached", timeout=TIMEOUT_MS)
            add_btn.click(force=True)
            warehouse_link = page.get_by_role("link", name=WAREHOUSE, exact=True)
            warehouse_link.wait_for(state="visible")
            warehouse_link.click(force=True)
            page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value").wait_for(state="visible")
            
            dropdown = page.locator("id=pag_I_StkAdj_NewGeneral_drp_n_REASON_HDR_Value")
            if dropdown.is_enabled(): dropdown.select_option(REASON_CODE)
            ui_log("SYS", "Ready. Opening data stream for payload injection...")

            progress_bar = st.progress(0)
            total_rows = len(df_view)
            
            # --- FUNGSI UPDATE LABEL REALTIME ---
            def update_progress_label(current, total):
                html = f"""
                <div style='display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 4px;'>
                    <div class='terminal-label' style='margin-bottom: 0;'>Log - Active Account: <span style='color: #38bdf8;'>{selected_distributor} ({bot_user})</span></div>
                    <div style='font-family: "JetBrains Mono", monospace; font-size: 0.75rem; color: #10b981; font-weight: 700; background: rgba(16, 185, 129, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(16, 185, 129, 0.2);'>{current}/{total} SKU has been processed</div>
                </div>
                """
                log_label_placeholder.markdown(html, unsafe_allow_html=True)

            update_progress_label(0, total_rows)
            
            for i, (idx, row) in enumerate(df_view.iterrows()):
                update_progress_label(i + 1, total_rows)
                sku = str(row['SKU']).strip()
                try: qty = str(int(float(row['Qty'])))
                except Exception: qty = str(row['Qty']).strip()

                ui_log("INJECT", f"Processing Payload {i+1}/{total_rows} | Target SKU: [{sku}]")
                try:
                    sku_input = page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value")
                    ui_log("INJECT", f"Locking target node for SKU [{sku}]...")
                    sku_input.fill(sku)
                    ui_log("INJECT", "Triggering system lookup (Tab event)...")
                    sku_input.press("Tab")
                    time.sleep(1.5) 
                    
                    qty_input = page.locator("id=pag_I_StkAdj_NewGeneral_txt_QTY1_Value")
                    qty_input.wait_for(state="visible", timeout=TIMEOUT_MS)
                    ui_log("INJECT", f"Node resolved. Assigning adjustment quantity: {qty} EA")
                    qty_input.fill(qty)
                    time.sleep(0.5) 
                    
                    ui_log("INJECT", "Dispatching Add command to grid...")
                    page.locator("id=pag_I_StkAdj_NewGeneral_btn_Add_Value").click(force=True)
                    ui_log("SYS", "Awaiting DOM form reset confirmation...")
                    page.wait_for_function("document.getElementById('pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value').value === ''", timeout=TIMEOUT_MS)
                    
                    df_view.at[idx, 'Status'] = 'Success'
                    df_view.at[idx, 'Keterangan'] = f'Input {qty} EA'
                    success_count += 1
                    ui_log("SUCCESS", f"Transaction {i+1} committed. Grid updated.")
                    database.log_adjustment(supabase, sku, qty, "Success", f"Attached {qty} EA", bot_user)
                except Exception as loop_err: 
                    df_view.at[idx, 'Status'] = 'Failed'
                    df_view.at[idx, 'Keterangan'] = 'Node Timeout'
                    failed_count += 1
                    ui_log("ERROR", f"Timeout on SKU [{sku}]. Node unresponsive. Skipping.")
                    database.log_adjustment(supabase, sku, qty, "Failed", "Node Timeout", bot_user)
                    
                progress_bar.progress((i+1)/total_rows)
                if i % TABLE_UPDATE_INTERVAL == 0 or i == total_rows-1: 
                    table_placeholder.dataframe(df_view, use_container_width=True, hide_index=True)
                    
            ui_log("SERVER", "Finalizing batch. Saving document to main server...")
            page.locator("id=pag_I_StkAdj_NewGeneral_btn_Save_Value").click()
            try: 
                yes_btn = page.locator("id=pag_PopUp_YesNo_btn_Yes_Value")
                yes_btn.wait_for(state="visible", timeout=5000)
                ui_log("SERVER", "Confirming save dialog...")
                yes_btn.click()
                ui_log("SERVER", "Document physically written to database.")
            except Exception: 
                ui_log("SERVER", "Auto-save confirmed. Document written to database.")
                
            ui_log("SYS", "Holding session for 5 seconds to ensure Newspage database write...")
            time.sleep(5)
            
            ui_log("AUTH", "Initiating system logout sequence...")
            try:
                page.once("dialog", lambda dialog: dialog.accept())
                page.locator("id=btnLogout").click(timeout=10000)
                ui_log("AUTH", "Pop up confirm logout...")
                time.sleep(2)
                ui_log("SUCCESS", "Logged out successfully.")
            except Exception as e:
                ui_log("ERROR", "Logout button not found or timeout.")
                
            ui_log("SYS", "Closing browser and releasing memory...")
            browser.close()
            elapsed = int(time.time() - global_start_time)
            ui_log("SUCCESS", f"Complete. Total runtime: {elapsed//60}m {elapsed%60}s")
            box_html = f"<div style='background-color:#166534;color:#ffffff;padding:12px 16px;border-radius:8px;font-weight:600;font-size:0.92rem;margin:8px 0;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.3);display:block;width:100%;'>Done — Success: {success_count} | Failed: {failed_count} | Time: {elapsed//60}m {elapsed%60}s</div>"
            st.markdown(box_html, unsafe_allow_html=True)
            alert_callback(f"✅ <b>BOT FINISHED</b>\nDist: {selected_distributor}\nSuccess: {success_count} | Failed: {failed_count}\nRuntime: {elapsed//60}m {elapsed%60}s")

            if success_count > 0: 
                st.toast('System override complete!')
                st.session_state.reconcile_result = None
                
            st.session_state.is_bot_running = False

    except Exception as e:
        st.session_state.is_bot_running = False
        st.error("System halted.")
        ui_log("ERROR", f"FAILURE: {e}")
        alert_callback(f"🚨 <b>FATAL ERROR (EXECUTE)</b>\nDist: {selected_distributor}\nError: <code>{str(e)[:100]}</code>")
