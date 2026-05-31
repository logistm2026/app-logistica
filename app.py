import streamlit as st
import pdfplumber
import pandas as pd
import requests
import re

WEBHOOK_URL = "https://hook.eu1.make.com/li2f2rnlf6kapo7qz37hzfm9aggg9too"

# --- FUNZIONE PER CREARE L'ID UNIVOCO ---
def genera_id(destinatario, ddt):
    # Rimuove gli spazi e mette in maiuscolo per evitare doppioni dovuti alla formattazione
    dest_pulito = str(destinatario).replace(" ", "").upper()
    ddt_pulito = str(ddt).replace(" ", "").upper()
    return f"{dest_pulito}-{ddt_pulito}"

# --- FUNZIONE DI ESTRAZIONE E FUSIONE ---
def elabora_dati(file_pdf, file_csv):
    spedizioni = {}

    # ==========================================
    # FASE 1: LETTURA PDF
    # ==========================================
    if file_pdf is not None:
        with pdfplumber.open(file_pdf) as pdf:
            for pagina in pdf.pages:
                testo = pagina.extract_text()
                if not testo:
                    continue
                
                righe = testo.split('\n')
                
                for i, riga in enumerate(righe):
                    # Cerchiamo il vecchio codice spedizione solo come "ancora" per trovare la riga
                    match_id = re.search(r'(\d{5}/\d{4}/[A-Z]+)', riga)
                    
                    if match_id:
                        try:
                            destinatario = righe[i+1].strip()
                            indirizzo = righe[i+2].strip()
                            
                            # Pulizia dati specifici
                            if "FEDRIGONI" in destinatario or "Corrispondente" in destinatario:
                                destinatario = righe[i+2].strip()
                                indirizzo = righe[i+3].strip()
                                # ATTENZIONE: Regola questi numeri (+4, +5) in base a dove si trovano Peso e DDT nel tuo PDF
                                peso = righe[i+4].strip() 
                                ddt = righe[i+5].strip()  
                            else:
                                # ATTENZIONE: Regola questi numeri (+3, +4)
                                peso = righe[i+3].strip() 
                                ddt = righe[i+4].strip()  

                            # Creiamo il nuovo ID indistruttibile
                            id_univoco = genera_id(destinatario, ddt)
                            
                            spedizioni[id_univoco] = {
                                "ID_Pacco": id_univoco,
                                "Destinatario": destinatario,
                                "Indirizzo": indirizzo,
                                "Peso_Lordo": peso,
                                "DDT": ddt
                            }
                        except IndexError:
                            pass

    # ==========================================
    # FASE 2: LETTURA CSV (Fonde e aggiorna)
    # ==========================================
    if file_csv is not None:
        # Assumiamo che il CSV usi il punto e virgola. Se usa la virgola, cambia sep=';' in sep=','
        df_csv = pd.read_csv(file_csv, sep=';', dtype=str).fillna("")
        
        for index, row in df_csv.iterrows():
            try:
                # ATTENZIONE: Inserisci qui i nomi ESATTI delle intestazioni del tuo file CSV
                destinatario_csv = row['RAGIONE SOCIALE DESTINATARIO']
                indirizzo_csv = row['INDIRIZZO']
                peso_csv = row['PESO LORDO']
                ddt_csv = row['DDT']
                
                if destinatario_csv == "":
                    continue
                
                # Creiamo lo stesso ID indistruttibile. Se esisteva nel PDF, i dati verranno aggiornati.
                id_univoco_csv = genera_id(destinatario_csv, ddt_csv)
                
                spedizioni[id_univoco_csv] = {
                    "ID_Pacco": id_univoco_csv,
                    "Destinatario": destinatario_csv,
                    "Indirizzo": indirizzo_csv,
                    "Peso_Lordo": peso_csv,
                    "DDT": ddt_csv
                }
            except KeyError as e:
                st.error(f"❌ Errore CSV: Non trovo la colonna {e}. Controlla i nomi esatti nel file.")
                return []

    return list(spedizioni.values())

# --- INTERFACCIA UTENTE ---
st.set_page_config(page_title="Hub Logistica", page_icon="📦")

st.title("📦 Hub Sincronizzazione Spedizioni")
st.write("Carica il PDF e/o il CSV. Il sistema unirà i dati usando Destinatario e DDT, eliminando i doppioni.")

col1, col2 = st.columns(2)
with col1:
    pdf_caricato = st.file_uploader("📄 Carica il PDF (Es. delle 18 o aggiornato)", type="pdf")
with col2:
    csv_caricato = st.file_uploader("📊 Carica il CSV (Es. delle 04:00)", type="csv")

if pdf_caricato is not None or csv_caricato is not None:
    if st.button("🚀 Fondi e Invia al Database"):
        with st.spinner('Elaborazione e fusione dei documenti in corso...'):
            try:
                pacchi_finali = elabora_dati(pdf_caricato, csv_caricato)
                
                if not pacchi_finali:
                    st.warning("Non ho trovato dati validi da elaborare.")
                else:
                    st.info(f"Trovate {len(pacchi_finali)} spedizioni univoche. Trasferimento in corso...")
                    
                    successi = 0
                    for pacco in pacchi_finali:
                        risposta = requests.post(WEBHOOK_URL, json=pacco)
                        if risposta.status_code == 200:
                            successi += 1
                            
                    if successi == len(pacchi_finali):
                        st.success(f"✅ Ottimo! {successi} spedizioni sincronizzate su Google Fogli.")
                    else:
                        st.warning(f"⚠️ Sincronizzazione parziale: {successi}/{len(pacchi_finali)}.")
            except Exception as e:
                st.error(f"Errore tecnico durante l'esecuzione: {e}")
