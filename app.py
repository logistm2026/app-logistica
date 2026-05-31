import streamlit as st
import pdfplumber
import pandas as pd
import re
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONNESSIONE A GOOGLE SHEETS ---
def connetti_google_sheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        # Leggiamo la chiave nascosta in modo sicuro
        creds_dict = json.loads(st.secrets["google_key"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        # INSERISCI QUI IL NOME ESATTO DEL TUO FILE GOOGLE E DEL FOGLIO
        foglio = client.open("Logistica Tracking").worksheet("Spedizioni") 
        return foglio
    except Exception as e:
        st.error(f"Errore di connessione a Google Fogli: {e}")
        return None

def genera_id(destinatario, ddt):
    dest_pulito = str(destinatario).replace(" ", "").upper()
    ddt_pulito = str(ddt).replace(" ", "").upper()
    return f"{dest_pulito}-{ddt_pulito}"

def elabora_dati(file_pdf, file_csv):
    spedizioni = {}

    if file_pdf is not None:
        with pdfplumber.open(file_pdf) as pdf:
            for pagina in pdf.pages:
                testo = pagina.extract_text()
                if not testo: continue
                righe = testo.split('\n')
                
                for i, riga in enumerate(righe):
                    if re.search(r'(\d{5}/\d{4}/[A-Z]+)', riga):
                        try:
                            destinatario = righe[i+1].strip()
                            indirizzo = righe[i+2].strip()
                            if "FEDRIGONI" in destinatario or "Corrispondente" in destinatario:
                                destinatario = righe[i+2].strip()
                                indirizzo = righe[i+3].strip()
                                peso = righe[i+4].strip() 
                                ddt = righe[i+5].strip()  
                            else:
                                peso = righe[i+3].strip() 
                                ddt = righe[i+4].strip()  

                            id_univoco = genera_id(destinatario, ddt)
                            spedizioni[id_univoco] = {"ID_Pacco": id_univoco, "Destinatario": destinatario, "Indirizzo": indirizzo, "Peso_Lordo": peso, "DDT": ddt}
                        except IndexError:
                            pass

    if file_csv is not None:
        df_csv = pd.read_csv(file_csv, sep=';', dtype=str).fillna("")
        for index, row in df_csv.iterrows():
            try:
                destinatario_csv = row['RAGIONE SOCIALE DESTINATARIO']
                indirizzo_csv = row['INDIRIZZO']
                peso_csv = row['PESO LORDO']
                ddt_csv = row['DDT']
                
                if destinatario_csv == "": continue
                id_univoco_csv = genera_id(destinatario_csv, ddt_csv)
                spedizioni[id_univoco_csv] = {"ID_Pacco": id_univoco_csv, "Destinatario": destinatario_csv, "Indirizzo": indirizzo_csv, "Peso_Lordo": peso_csv, "DDT": ddt_csv}
            except KeyError as e:
                pass

    return list(spedizioni.values())

# --- SINCRONIZZAZIONE DIRETTA ---
def invia_dati_a_google(pacchi_finali):
    foglio = connetti_google_sheets()
    if foglio is None: return False

    st.write("Connesso al database. Analisi dei dati in corso...")
    
    # Leggiamo tutto il foglio per capire quali pacchi esistono già
    tutti_i_dati = foglio.get_all_records()
    intestazioni = foglio.row_values(1) # Prende i nomi esatti delle tue colonne in riga 1
    
    # Creiamo una mappa per trovare subito le righe da aggiornare
    # L'indice parte da 0, +2 perché Excel parte da riga 1 (che è l'intestazione)
    mappa_righe = {str(riga.get("ID_Pacco", "")): idx + 2 for idx, riga in enumerate(tutti_i_dati)}
    
    successi = 0
    for pacco in pacchi_finali:
        id_pacco = pacco["ID_Pacco"]
        
        # Allineiamo i nostri dati sotto le colonne corrette di Google Fogli
        nuova_riga = []
        for colonna in intestazioni:
            nuova_riga.append(pacco.get(colonna, ""))
            
        if id_pacco in mappa_righe:
            # Sovrascrive i dati esistenti senza toccare le note o lo stato del corriere
            riga_da_aggiornare = mappa_righe[id_pacco]
            foglio.update(f"A{riga_da_aggiornare}:E{riga_da_aggiornare}", [nuova_riga[:5]])
        else:
            # Aggiunge in fondo al file
            foglio.append_row(nuova_riga)
            
        successi += 1
        
    return successi

# --- INTERFACCIA UTENTE ---
st.set_page_config(page_title="Hub Logistica", page_icon="📦")
st.title("📦 Hub Sincronizzazione Spedizioni")

col1, col2 = st.columns(2)
with col1:
    pdf_caricato = st.file_uploader("📄 Carica il PDF", type="pdf")
with col2:
    csv_caricato = st.file_uploader("📊 Carica il CSV", type="csv")

if pdf_caricato is not None or csv_caricato is not None:
    if st.button("🚀 Fondi e Scrivi su Google Fogli"):
        with st.spinner('Elaborazione in corso...'):
            pacchi_finali = elabora_dati(pdf_caricato, csv_caricato)
            if not pacchi_finali:
                st.warning("Non ho trovato dati validi da elaborare.")
            else:
                successi = invia_dati_a_google(pacchi_finali)
                if successi:
                    st.success(f"✅ Ottimo! {successi} spedizioni sincronizzate direttamente a costo zero!")
