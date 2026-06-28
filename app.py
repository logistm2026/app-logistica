import streamlit as st
import pandas as pd
import json
import gspread
import hashlib
import pytz
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

st.set_page_config(page_title="Hub Logistica", page_icon="📦", layout="centered")

# --- NASCONDI INTERFACCIA STREAMLIT ---
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

# --- CONNESSIONE A GOOGLE SHEETS ---
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

# --- GENERATORE ID UNIVOCO BASE ---
def genera_id(destinatario, indirizzo, peso, ddt):
    stringa_base = f"{str(destinatario).strip().upper()}-{str(indirizzo).strip().upper()}-{str(peso).strip()}-{str(ddt).strip().upper()}"
    codice_univoco = hashlib.md5(stringa_base.encode()).hexdigest()[:8].upper()
    return codice_univoco

# --- FUNZIONE DI ELABORAZIONE MODIFICATA (STRADA 2) ---
def elabora_dati(file_fbn, file_csv, mappa_stati_esistenti):
    spedizioni = {}
    
    fuso_italia = pytz.timezone('Europe/Rome')
    timestamp_run = datetime.now(fuso_italia).strftime("%Y%m%d_%H%M")
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
                destinatario = str(row.iloc[3]).strip()
                if not destinatario: continue
                
                ddt = str(row.iloc[0]).strip()
                via = str(row.iloc[4]).strip()
                civico = str(row.iloc[5]).strip()
                cap = str(row.iloc[6]).strip().zfill(5) if str(row.iloc[6]).strip() else ""
                citta = str(row.iloc[7]).strip()
                prov = str(row.iloc[8]).strip()
                
                indirizzo_completo = f"{via} {civico} {cap} {citta} {prov}".strip()
                indirizzo_completo = " ".join(indirizzo_completo.split()) 
                
                colli = str(row.iloc[9]).strip() if len(row) > 9 else "1"
                
                peso_grezzo = str(row.iloc[10]).strip()
                peso = peso_grezzo.replace('.', ',')
                
                # Generazione ID Base
                id_univoco_base = genera_id(destinatario, indirizzo_completo, peso, ddt)
                
                # CONTROLLO SOVRASCRITTURA STORICO (Logica Strada 2)
                id_univoco = id_univoco_base
                versione = 2
                # Se l'ID esiste e lo stato non è "In Magazzino", è un ordine vecchio. Creiamo una nuova versione.
                while id_univoco in mappa_stati_esistenti and mappa_stati_esistenti[id_univoco] not in ["In Magazzino", ""]:
                    id_univoco = f"{id_univoco_base}_V{versione}"
                    versione += 1
                
                ordinamento = f"{timestamp_run}_{str(contatore).zfill(3)}"
                contatore += 1
                
                spedizioni[id_univoco] = {
                    "ID_Pacco": id_univoco, 
                    "Ordinamento": ordinamento,
                    "Destinatario": destinatario, 
                    "Indirizzo": indirizzo_completo, 
                    "Colli": colli, 
                    "Peso Lordo": peso, 
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
                destinatario_csv = str(row.get('RAGIONE SOCIALE DESTINATARIO', '')).strip()
                if destinatario_csv == "": continue
                
                via_csv = str(row.get('INDIRIZZO', '')).strip()
                cap_grezzo = str(row.get('CAP', '')).strip()
                localita_csv = str(row.get('LOCALITA', '')).strip()
                provincia_csv = str(row.get('PROVINCIA', '')).strip()
                
                cap_csv = cap_grezzo.zfill(5) if cap_grezzo else ""
                
                indirizzo_csv = f"{via_csv} {cap_csv} {localita_csv} {provincia_csv}".strip()
                indirizzo_csv = " ".join(indirizzo_csv.split())
                
                colli_csv = str(row.get('TOTALE COLLI', '1')).strip()
                
                peso_csv_grezzo = str(row.get('PESO LORDO', row.get('Peso Lordo', '0'))).strip()
                peso_csv = peso_csv_grezzo.replace('.', ',')
                
                ddt_csv = str(row.get('DDT', '')).strip()
                
                # Generazione ID Base per CSV
                id_univoco_base_csv = genera_id(destinatario_csv, indirizzo_csv, peso_csv, ddt_csv)
                
                # CONTROLLO SOVRASCRITTURA STORICO (Logica Strada 2)
                id_univoco_csv = id_univoco_base_csv
                versione = 2
                while id_univoco_csv in mappa_stati_esistenti and mappa_stati_esistenti[id_univoco_csv] not in ["In Magazzino", ""]:
                    id_univoco_csv = f"{id_univoco_base_csv}_V{versione}"
                    versione += 1
                
                ordinamento_csv = f"{timestamp_run}_{str(contatore).zfill(3)}"
                contatore += 1
                
                spedizioni[id_univoco_csv] = {
                    "ID_Pacco": id_univoco_csv, 
                    "Ordinamento": ordinamento_csv,
                    "Destinatario": destinatario_csv, 
                    "Indirizzo": indirizzo_csv, 
                    "Colli": colli_csv, 
                    "Peso Lordo": peso_csv, 
                    "DDT": ddt_csv,
                    "Stato": "In Magazzino",
                    "Email_Operatore": "logist.m2026@gmail.com",
                    "Fornitore": "FBN"
                }
        except Exception as e:
             st.error(f"Errore nella lettura del tuo CSV: {e}")

    return list(spedizioni.values())

# --- SINCRONIZZAZIONE DIRETTA ---
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
st.title("📦 Hub Sincronizzazione Spedizioni")
st.markdown("Carica le distinte dei corrieri per sincronizzarle istantaneamente con Google Fogli.")

col1, col2 = st.columns(2)
with col1:
    file_fbn = st.file_uploader("📄 Carica File FBN (Excel/CSV)", type=["xlsx", "xls", "csv"])
with col2:
    file_csv_tuo = st.file_uploader("📊 Carica il tuo CSV", type=["csv"])

if file_fbn is not None or file_csv_tuo is not None:
    if st.button("🚀 Fondi e Scrivi su Google Fogli", use_container_width=True):
        
        # 1. LETTURA STATO PRECEDENTE DAL DATABASE
        mappa_stati_esistenti = {}
        with st.spinner('Analisi dello storico database in corso...'):
            doc_google = connetti_google_sheets()
            if doc_google:
                try:
                    foglio_spedizioni = doc_google.worksheet("Spedizioni")
                    tutti_i_dati_esistenti = foglio_spedizioni.get_all_records()
                    # Creiamo la mappa leggendo gli ID e lo Stato attuale
                    mappa_stati_esistenti = {str(riga.get("ID_Pacco", "")): str(riga.get("Stato", "")) for riga in tutti_i_dati_esistenti}
                except Exception as e:
                    st.warning("Foglio 'Spedizioni' vuoto o non accessibile. Procedo come primo avvio.")

        # 2. ELABORAZIONE E SCRITTURA
        with st.spinner('Elaborazione super-veloce in corso...'):
            # Passiamo la mappa alla funzione elabora_dati
            pacchi_finali = elabora_dati(file_fbn, file_csv_tuo, mappa_stati_esistenti)
            
            if not pacchi_finali:
                st.warning("Non ho trovato dati validi da elaborare.")
            else:
                successi = invia_dati_a_google(pacchi_finali)
                if successi:
                    st.success(f"✅ Ottimo! {successi} spedizioni sincronizzate perfettamente!")
