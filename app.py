import streamlit as st
import pandas as pd
import json
import gspread
import hashlib
from oauth2client.service_account import ServiceAccountCredentials

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

# --- GENERATORE ID UNIVOCO ---
def genera_id(destinatario, indirizzo, peso, ddt):
    stringa_base = f"{str(destinatario).strip().upper()}-{str(indirizzo).strip().upper()}-{str(peso).strip()}-{str(ddt).strip().upper()}"
    codice_univoco = hashlib.md5(stringa_base.encode()).hexdigest()[:8].upper()
    return codice_univoco

# --- FUNZIONE DI ELABORAZIONE (100% EXCEL/CSV) ---
def elabora_dati(file_fbn, file_csv):
    spedizioni = {}

    # ==========================================
    # 1. LETTURA FILE FBN (Excel o CSV)
    # ==========================================
    if file_fbn is not None:
        try:
            # Capisce automaticamente se hai caricato un Excel o un CSV
            if file_fbn.name.endswith('.csv'):
                df_fbn = pd.read_csv(file_fbn, dtype=str).fillna("")
            else:
                df_fbn = pd.read_excel(file_fbn, dtype=str).fillna("")

            for index, row in df_fbn.iterrows():
                # USIAMO GLI INDICI NUMERICI (iloc) PER AGGIRARE LE COLONNE COL NOME DOPPIO!
                # Col 0: DDT | Col 3: Nome | Col 4: Via | Col 5: Civico | Col 6: CAP | Col 7: Città | Col 8: Prov | Col 10: Peso
                destinatario = str(row.iloc[3]).strip()
                if not destinatario: continue # Salta le righe vuote
                
                ddt_grezzo = str(row.iloc[0]).strip()
                ddt = ddt_grezzo if ddt_grezzo.isdigit() else ""
                
                via = str(row.iloc[4]).strip()
                civico = str(row.iloc[5]).strip()
                cap = str(row.iloc[6]).strip().zfill(5) if str(row.iloc[6]).strip() else ""
                citta = str(row.iloc[7]).strip()
                prov = str(row.iloc[8]).strip()
                
                # Unisce l'indirizzo e rimuove doppi spazi se manca il civico
                indirizzo_completo = f"{via} {civico} {cap} {citta} {prov}".strip()
                indirizzo_completo = " ".join(indirizzo_completo.split()) 
                
                peso = str(row.iloc[10]).strip()
                
                id_univoco = genera_id(destinatario, indirizzo_completo, peso, ddt)
                
                spedizioni[id_univoco] = {
                    "ID_Pacco": id_univoco, 
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
                
                peso_csv = str(row.get('PESO LORDO', row.get('Peso Lordo', '0'))).strip()
                ddt_csv_grezzo = str(row.get('DDT', '')).strip()
                
                ddt_csv = ddt_csv_grezzo if ddt_csv_grezzo.isdigit() else ""
                
                id_univoco_csv = genera_id(destinatario_csv, indirizzo_csv, peso_csv, ddt_csv)
                spedizioni[id_univoco_csv] = {
                    "ID_Pacco": id_univoco_csv, 
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
                'range': f'A{riga_num}:E{riga_num}',
                'values': [nuova_riga[:5]]
            })
        else:
            da_inserire.append(nuova_riga)
            
    successi = 0
    
    try:
        if da_aggiornare:
            foglio.batch_update(da_aggiornare, value_input_option="USER_ENTERED")
            successi += len(da_aggiornare)
            
        if da_inserire:
            foglio.append_rows(da_inserire, value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
            successi += len(da_inserire)
            
        return successi
    except Exception as e:
        st.error(f"Errore Tecnico con Google Fogli: {e}")
        return successi

# --- INTERFACCIA UTENTE ---
st.set_page_config(page_title="Hub Logistica", page_icon="📦", layout="centered")
st.title("📦 Hub Sincronizzazione Spedizioni")
st.markdown("Carica le distinte dei corrieri per sincronizzarle istantaneamente con Google Fogli.")

col1, col2 = st.columns(2)
with col1:
    # ORA ACCETTA EXCEL E CSV DA FBN!
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
