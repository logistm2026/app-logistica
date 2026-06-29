import streamlit as st
import pandas as pd
import json
import gspread
import hashlib
import pytz
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

st.set_page_config(page_title="Hub Logistica", page_icon="📦", layout="centered")

# NASCONDI INTERFACCIA STREAMLIT
nascondi_menu = """
    <style>
    [data-testid="stToolbar"] {visibility: hidden !important;}
    [data-testid="stHeader"] {visibility: hidden !important;}
    [data-testid="stDecoration"] {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    [data-testid="stFooter"] {visibility: hidden !important;}
    </style>
    """
st.markdown(nascondi_menu, unsafe_allow_html=True)

# CONNESSIONE A GOOGLE SHEETS
def connetti_google_sheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["google_key"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("Logistica Tracking") 
    except Exception as e:
        st.error(f"Errore di connessione a Google Fogli: {e}")
        return None

# UTILITY: PULIZIA TESTO
def pulisci_testo(valore):
    """Rimuove spazi duplicati e il '.0' dei numeri interi letti come float"""
    val = " ".join(str(valore).strip().split()).upper()
    if val.endswith('.0'):
        val = val[:-2]
    return val

# FUNZIONE DI ELABORAZIONE (CONTROLLO SOLO SU DESTINATARIO E DDT)
def elabora_dati(file_fbn, file_csv, righe_recenti_database):
    spedizioni = {}
    
    fuso_italia = pytz.timezone('Europe/Rome')
    data_oggi_assoluta = datetime.now(fuso_italia)
    timestamp_run = data_oggi_assoluta.strftime("%Y%m%d_%H%M")
    contatore = 1

    # ==========================================
    # 1. LETTURA FILE FBN
    # ==========================================
    if file_fbn is not None:
        try:
            if file_fbn.name.endswith('.csv'):
                df_fbn = pd.read_csv(file_fbn, dtype=str).fillna("")
            else:
                df_fbn = pd.read_excel(file_fbn, dtype=str).fillna("")

            for index, row in df_fbn.iterrows():
                destinatario = pulisci_testo(row.iloc[3])
                if not destinatario: continue
                
                ddt = pulisci_testo(row.iloc[0])
                
                via = str(row.iloc[4]).strip()
                civico = pulisci_testo(row.iloc[5])
                cap = str(row.iloc[6]).strip().zfill(5) if str(row.iloc[6]).strip() else ""
                citta = str(row.iloc[7]).strip()
                prov = str(row.iloc[8]).strip()
                
                indirizzo_completo = f"{via} {civico} {cap} {citta} {prov}".strip()
                indirizzo_completo = " ".join(indirizzo_completo.split()) 
                
                colli = pulisci_testo(row.iloc[9]) if len(row) > 9 else "1"
                
                peso_grezzo = str(row.iloc[10]).strip()
                peso_per_foglio = peso_grezzo.replace('.', ',') 
                
                # IMPRONTA BLINDATA: Solo Destinatario e DDT
                impronta_corrente = f"{destinatario}-{ddt}"
                
                id_pacco = None
                
                # Coda di Consumo
                for idx, riga_db in enumerate(righe_recenti_database):
                    if riga_db["impronta"] == impronta_corrente:
                        id_pacco = riga_db["ID_Pacco"]
                        # Consuma il record per gestire correttamente i multi-collo
                        righe_recenti_database.pop(idx)
                        break
                
                if id_pacco is None:
                    id_pacco = f"{timestamp_run}_{str(contatore).zfill(3)}"
                    contatore += 1
                
                spedizioni[id_pacco] = {
                    "ID_Pacco": id_pacco, 
                    "Ordinamento": id_pacco,
                    "Destinatario": destinatario, 
                    "Indirizzo": indirizzo_completo, 
                    "Colli": colli, 
                    "Peso Lordo": peso_per_foglio, 
                    "DDT": ddt,
                    "Stato": "In Magazzino",
                    "Email_Operatore": "logist.m2026@gmail.com",
                    "Fornitore": "FBN"
                }
        except Exception as e:
            st.error(f"Errore nella lettura del file FBN: {e}")

    # ==========================================
    # 2. LETTURA DEL TUO CSV
    # ==========================================
    if file_csv is not None:
        try:
            df_csv = pd.read_csv(file_csv, sep=';', dtype=str).fillna("")
            for index, row in df_csv.iterrows():
                destinatario_csv = pulisci_testo(row.get('RAGIONE SOCIALE DESTINATARIO', ''))
                if not destinatario_csv: continue
                
                via_csv = str(row.get('INDIRIZZO', '')).strip()
                cap_grezzo = pulisci_testo(row.get('CAP', ''))
                localita_csv = str(row.get('LOCALITA', '')).strip()
                provincia_csv = str(row.get('PROVINCIA', '')).strip()
                
                cap_csv = cap_grezzo.zfill(5) if cap_grezzo else ""
                
                indirizzo_csv = f"{via_csv} {cap_csv} {localita_csv} {provincia_csv}".strip()
                indirizzo_csv = " ".join(indirizzo_csv.split())
                
                colli_csv = pulisci_testo(row.get('TOTALE COLLI', '1'))
                
                peso_csv_grezzo = str(row.get('PESO LORDO', row.get('Peso Lordo', '0'))).strip()
                peso_csv_per_foglio = peso_csv_grezzo.replace('.', ',')
                
                ddt_csv = pulisci_testo(row.get('DDT', ''))
                
                # IMPRONTA BLINDATA CSV
                impronta_corrente_csv = f"{destinatario_csv}-{ddt_csv}"
                
                id_pacco_csv = None
                
                for idx, riga_db in enumerate(righe_recenti_database):
                    if riga_db["impronta"] == impronta_corrente_csv:
                        id_pacco_csv = riga_db["ID_Pacco"]
                        righe_recenti_database.pop(idx)
                        break
                
                if id_pacco_csv is None:
                    id_pacco_csv = f"{timestamp_run}_{str(contatore).zfill(3)}"
                    contatore += 1
                
                spedizioni[id_pacco_csv] = {
                    "ID_Pacco": id_pacco_csv, 
                    "Ordinamento": id_pacco_csv,
                    "Destinatario": destinatario_csv, 
                    "Indirizzo": indirizzo_csv, 
                    "Colli": colli_csv, 
                    "Peso Lordo": peso_csv_per_foglio, 
                    "DDT": ddt_csv,
                    "Stato": "In Magazzino",
                    "Email_Operatore": "logist.m2026@gmail.com",
                    "Fornitore": "FBN"
                }
        except Exception as e:
             st.error(f"Errore nella lettura del tuo CSV: {e}")

    return list(spedizioni.values())

# SINCRONIZZAZIONE DIRETTA
def invia_dati_a_google(pacchi_finali):
    doc_google = connetti_google_sheets()
    if doc_google is None: return False

    foglio_spedizioni = doc_google.worksheet("Spedizioni")
    st.write("Sincronizzazione in blocco in corso...")
    
    tutti_i_dati = foglio_spedizioni.get_all_records()
    intestazioni = foglio_spedizioni.row_values(1) 
    
    try:
        foglio_storico = doc_google.worksheet("Storico")
        intestazioni_storico = foglio_storico.row_values(1)
    except Exception:
        foglio_storico = None
        intestazioni_storico = []
        st.warning("⚠️ Impossibile accedere alla scheda 'Storico'. Lo storico eventi non verrà registrato.")
    
    mappa_righe = {str(riga.get("ID_Pacco", "")): idx + 2 for idx, riga in enumerate(tutti_i_dati)}
    
    da_aggiornare = []
    da_inserire = []
    da_inserire_storico = []
    
    fuso_italia = pytz.timezone('Europe/Rome')
    ora_attuale_storico = datetime.now(fuso_italia).strftime("%d/%m/%Y %H:%M:%S")
    
    for idx, pacco in enumerate(pacchi_finali):
        id_pacco = pacco["ID_Pacco"]
        nuova_riga = []
        for colonna in intestazioni:
            nuova_riga.append(pacco.get(colonna, ""))
            
        if id_pacco in mappa_righe:
            riga_num = mappa_righe[id_pacco]
            da_aggiornare.append({
                'range': f'A{riga_num}:A{riga_num}', 
                'values': [nuova_riga]
            })
        else:
            da_inserire.append(nuova_riga)
            
        if foglio_storico and intestazioni_storico:
            id_storico = hashlib.md5(f"{id_pacco}-{ora_attuale_storico}-{idx}".encode()).hexdigest()[:8].upper()
            riga_st = []
            for col in intestazioni_storico:
                col_clean = col.strip().lower().replace("_", " ")
                if col_clean == "id storico":
                    riga_st.append(id_storico)
                elif col_clean == "id pacco":
                    riga_st.append(id_pacco)
                elif col_clean in ["stato registrato", "stato_registrato"]:
                    riga_st.append("In Magazzino")
                elif col_clean in ["data ora", "data_ora"]:
                    riga_st.append(ora_attuale_storico)
                elif col_clean == "operatore":
                    riga_st.append("logist.m2026@gmail.com")
                else:
                    riga_st.append("")
            da_inserire_storico.append(riga_st)
            
    successi = 0
    
    try:
        if da_aggiornare:
            lettera_finale = chr(ord('A') + len(intestazioni) - 1)
            da_aggiornare_fix = []
            for item in da_aggiornare:
                riga_n = item['range'].split(':')[0][1:]
                da_aggiornare_fix.append({
                    'range': f'A{riga_n}:{lettera_finale}{riga_n}',
                    'values': item['values']
                })
            foglio_spedizioni.batch_update(da_aggiornare_fix, value_input_option="USER_ENTERED")
            successi += len(da_aggiornare_fix)
            
        if da_inserire:
            foglio_spedizioni.append_rows(da_inserire, value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
            successi += len(da_inserire)
            
        if da_inserire_storico:
            foglio_storico.append_rows(da_inserire_storico, value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
            
        return successi
    except Exception as e:
        st.error(f"Errore Tecnico con Google Fogli: {e}")
        return successi

# --- INTERFACCIA UTENTE ---
st.title("Hub Sincronizzazione Spedizioni")
st.markdown("Carica i file Excel e CSV per sincronizzarli istantaneamente con il Database.")

col1, col2 = st.columns(2)
with col1:
    file_fbn = st.file_uploader("📄 Carica File FBN (Excel)", type=["xlsx", "xls", "csv"])
with col2:
    file_csv_tuo = st.file_uploader("📊 Carica File Fedrigoni (CSV)", type=["csv"])

if file_fbn is not None or file_csv_tuo is not None:
    if st.button("🚀 Fondi e Scrivi su Google Fogli", use_container_width=True):
        
        righe_recenti_database = []
        with st.spinner('Analisi dello storico database in corso...'):
            doc_google = connetti_google_sheets()
            if doc_google:
                try:
                    foglio_spedizioni = doc_google.worksheet("Spedizioni")
                    tutti_i_dati_esistenti = foglio_spedizioni.get_all_records()
                    
                    fuso_italia = pytz.timezone('Europe/Rome')
                    data_oggi_assoluta = datetime.now(fuso_italia)
                    
                    for riga in tutti_i_dati_esistenti:
                        id_pacco_remoto = str(riga.get("ID_Pacco", ""))
                        
                        try:
                            data_remota_str = id_pacco_remoto.split("_")[0]
                            data_remota_obj = datetime.strptime(data_remota_str, "%Y%m%d").replace(tzinfo=fuso_italia)
                            giorni_trascorsi = (data_oggi_assoluta - data_remota_obj).days
                        except:
                            giorni_trascorsi = 0
                        
                        # SCUDO DEI 3 GIORNI + STATO ATTIVO
                        if giorni_trascorsi > 3 or str(riga.get("Stato", "")) not in ["In Magazzino", ""]:
                            continue
                            
                        dest = pulisci_testo(riga.get("Destinatario", ""))
                        ddt = pulisci_testo(riga.get("DDT", ""))
                        
                        if not dest or not ddt: continue
                        
                        # Impronta per la lista di coda: Solo Destinatario e DDT
                        impronta_ram = f"{dest}-{ddt}"
                        
                        righe_recenti_database.append({
                            "ID_Pacco": id_pacco_remoto,
                            "impronta": impronta_ram
                        })
                except Exception as e:
                    st.warning("Errore durante l'analisi preliminare. Procedo come primo avvio.")

        with st.spinner('Elaborazione super-veloce in corso...'):
            pacchi_finali = elabora_dati(file_fbn, file_csv_tuo, righe_recenti_database)
            
            if not pacchi_finali:
                st.warning("Non ho trovato dati validi da elaborare.")
            else:
                successi = invia_dati_a_google(pacchi_finali)
                if successi:
                    st.success(f"✅ Fatto! {successi} spedizioni sincronizzate perfettamente!")
