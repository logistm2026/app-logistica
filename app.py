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
'''
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
'''
# --- FUNZIONE A RAGGI X PER IL PDF ---
def elabora_dati(file_pdf, file_csv):
    if file_pdf is not None:
        with pdfplumber.open(file_pdf) as pdf:
            # Legge solo la prima pagina per fare il test
            testo = pdf.pages[0].extract_text()
            if not testo:
                st.error("Il PDF sembra vuoto o è un'immagine non leggibile.")
                return []
                
            righe = testo.split('\n')
            
            for i, riga in enumerate(righe):
                # Cerca l'ID della spedizione
                if re.search(r'(\d{5}/\d{4}/[A-Z]+)', riga):
                    st.error("🚨 STOP! Ho trovato il primo pacco. Ecco come il computer vede le righe:")
                    st.info(f"**ANCORA (Riga 0):** {riga}")
                    
                    # Stampa le 8 righe successive per vedere dove finiscono i dati
                    for j in range(1, 9):
                        try:
                            st.write(f"**+ {j} riga:** {righe[i+j].strip()}")
                        except IndexError:
                            pass
                    
                    st.warning("Fai uno screenshot di questa lista e mandamelo. Poi blocchiamo il codice!")
                    st.stop() # Ferma l'app all'istante
                    
    return []

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
    
    # Smistiamo i pacchi: quali sono da aggiornare e quali nuovi?
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
    
    # ESECUZIONE BATCH (Anti-blocco e copia formattazione)
    try:
        if da_aggiornare:
            foglio.batch_update(da_aggiornare, value_input_option="USER_ENTERED")
            successi += len(da_aggiornare)
            
        if da_inserire:
            # Il parametro INSERT_ROWS fa la magia: spinge giù le righe copiando bordi e colori
            foglio.append_rows(da_inserire, value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
            successi += len(da_inserire)
            
        return successi
    except Exception as e:
        st.error(f"Errore Tecnico con Google Fogli: {e}")
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
