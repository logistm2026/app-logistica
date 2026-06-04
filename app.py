import streamlit as st
import pandas as pd
import json
import gspread
import hashlib
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime # Aggiunto per gestire data e ora

st.set_page_config(page_title="Hub Logistica", page_icon="📦", layout="centered")

# --- CONNESSIONE A GOOGLE SHEETS ---
def connetti_google_sheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["google_key"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        foglio = client.open("Logistica Tracking").worksheet("Spedizioni") 
        return foglio
    except Exception as e:
        st.error(f"Errore di connessione a Google Fogli: {e}")
        return None

# --- GENERATORE ID UNIVOCO (NON TOCCARE: Scudo Anti-Doppioni) ---
def genera_id(destinatario, indirizzo, peso, ddt):
    stringa_base = f"{str(destinatario).strip().upper()}-{str(indirizzo).strip().upper()}-{str(peso).strip()}-{str(ddt).strip().upper()}"
    codice_univoco = hashlib.md5(stringa_base.encode()).hexdigest()[:8].upper()
    return codice_univoco

# --- FUNZIONE DI ELABORAZIONE ---
def elabora_dati(file_fbn, file_csv):
    spedizioni = {}
    
    # Creiamo un "timbro" del momento esatto in cui hai cliccato il pulsante (es. 20260604_1807)
    timestamp_run = datetime.now().strftime("%Y%m%d_%H%M")
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
                
                peso_grezzo = str(row.iloc[10]).strip()
                peso = peso_grezzo.replace('.', ',')
                
                id_univoco = genera_id(destinatario, indirizzo_completo, peso, ddt)
                
                # Generiamo la stringa progressiva per l'ordinamento di Autocrat
                ordinamento = f"{timestamp_run}_{str(contatore).zfill(3)}"
                contatore += 1
                
                spedizioni[id_univoco] = {
                    "ID_Pacco": id_univoco, 
                    "Ordinamento": ordinamento, # LA NUOVA COLONNA
                    "Destinatario": destinatario, 
                    "Indirizzo": indirizzo_completo, 
                    "Peso Lordo": peso, 
                    "DDT": ddt
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
                
                peso_csv_grezzo = str(row.get('PESO LORDO', row.get('Peso Lordo', '0'))).strip()
                peso_csv = peso_csv_grezzo.replace('.', ',')
                
                ddt_csv = str(row.get('DDT', '')).strip()
                
                id_univoco_csv = genera_id(destinatario_csv, indirizzo_csv, peso_csv, ddt_csv)
                
                # Continuiamo ad aumentare il contatore per non rompere l'ordine
                ordinamento_csv = f"{timestamp_run}_{str(contatore).zfill(3)}"
                contatore += 1
                
                spedizioni[id_univoco_csv] = {
                    "ID_Pacco": id_univoco_csv, 
                    "Ordinamento": ordinamento_csv, # LA NUOVA COLONNA
                    "Destinatario": destinatario_csv, 
                    "Indirizzo": indirizzo_csv, 
                    "Peso Lordo": peso_csv, 
                    "DDT": ddt_csv
                }
        except Exception as e:
             st.error(f"Errore nella lettura del tuo CSV: {e}")

    return list(spedizioni.values())

# --- SINCRONIZZAZIONE DIRETTA ---
def invia_dati_a_google(pacchi_finali):
    foglio = connetti_google_sheets()
    if foglio is None: return False

    st.write("Connesso al database. Sincronizzazione in blocco in corso...")
    
    tutti_i_dati = foglio.get_all_records()
    intestazioni = foglio.row_values(1) 
    
    # Se per caso non hai ancora la colonna "Ordinamento" sul foglio, eviterà errori
    if "Ordinamento" not in intestazioni:
        st.warning("⚠️ Promemoria: Ricordati di aggiungere una colonna chiamata 'Ordinamento' su Google Fogli!")
    
    mappa_righe = {str(riga.get("ID_Pacco", "")): idx + 2 for idx, riga in enumerate(tutti_i_dati)}
    
    da_aggiornare = []
    da_inserire = []
    
    for pacco in pacchi_finali:
        id_pacco = pacco["ID_Pacco"]
        nuova_riga = []
        for colonna in intestazioni:
            nuova_riga.append(pacco.get(colonna, ""))
            
        if id_pacco in mappa_righe:
            riga_num = mappa_righe[id_pacco]
            da_aggiornare.append({
                'range': f'A{riga_num}:E{riga_num}',  # ATTENZIONE: Se hai aggiunto una colonna, verifica che "E" copra tutto il range. Potresti dover mettere 'A{riga_num}:F{riga_num}' o 'Z{riga_num}'. Il codice di update potrebbe tagliare l'ultima colonna se non è dinamico.
                'values': [nuova_riga]
            })
        else:
            da_inserire.append(nuova_riga)
            
    successi = 0
    
    try:
        if da_aggiornare:
            # FIX: Calcola dinamicamente la lettera finale della colonna in base a quante intestazioni hai
            lettera_finale = chr(ord('A') + len(intestazioni) - 1)
            da_aggiornare_fix = []
            for item in da_aggiornare:
                riga_n = item['range'].split(':')[0][1:]
                da_aggiornare_fix.append({
                    'range': f'A{riga_n}:{lettera_finale}{riga_n}',
                    'values': item['values']
                })
            foglio.batch_update(da_aggiornare_fix, value_input_option="USER_ENTERED")
            successi += len(da_aggiornare_fix)
            
        if da_inserire:
            foglio.append_rows(da_inserire, value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
            successi += len(da_inserire)
            
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
        with st.spinner('Elaborazione super-veloce in corso...'):
            pacchi_finali = elabora_dati(file_fbn, file_csv_tuo)
            if not pacchi_finali:
                st.warning("Non ho trovato dati validi da elaborare.")
            else:
                successi = invia_dati_a_google(pacchi_finali)
                if successi:
                    st.success(f"✅ Ottimo! {successi} spedizioni sincronizzate perfettamente al primo colpo!")
