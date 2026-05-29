import streamlit as st
import pdfplumber
import pandas as pd
import requests
import re

# Sostituisci questo link con quello che ti ha generato il modulo Webhook di Make.com
WEBHOOK_URL = "https://hook.eu1.make.com/li2f2rnlf6kapo7qz37hzfm9aggg9too"

# --- FUNZIONE PER LEGGERE IL PDF ---
def estrai_dati_pdf(file_pdf):
    dati_estratti = []
    
    with pdfplumber.open(file_pdf) as pdf:
        for pagina in pdf.pages:
            testo = pagina.extract_text()
            if not testo:
                continue
            
            righe = testo.split('\n')
            id_corrente = None
            
            for i, riga in enumerate(righe):
                # Cerchiamo il codice spedizione (es. 43607/2026/SE)
                match_id = re.search(r'(\d{5}/\d{4}/[A-Z]+)', riga)
                
                if match_id:
                    id_corrente = match_id.group(1)
                    try:
                        destinatario = righe[i+1].strip()
                        indirizzo = righe[i+2].strip()
                        
                        # Pulizia dati specifici
                        if "FEDRIGONI" in destinatario or "Corrispondente" in destinatario:
                            destinatario = righe[i+2].strip()
                            indirizzo = righe[i+3].strip()
                            
                        dati_estratti.append({
                            "ID_Pacco": id_corrente,
                            "Destinatario": destinatario,
                            "Indirizzo": indirizzo
                        })
                    except IndexError:
                        pass

    # Rimuoviamo i doppioni letti per sbaglio sulla stessa pagina
    df = pd.DataFrame(dati_estratti)
    df = df.drop_duplicates(subset=['ID_Pacco'])
    return df.to_dict('records')

# --- INTERFACCIA UTENTE ---
st.set_page_config(page_title="Importazione Logistica", page_icon="📦")

st.title("📦 Caricamento Liste di Carico")
st.write("Carica il PDF per inviare automaticamente le spedizioni al database.")

file_caricato = st.file_uploader("Trascina qui il file PDF", type="pdf")

if file_caricato is not None:
    if st.button("🚀 Invia al Database"):
        with st.spinner('Lettura del PDF in corso...'):
            try:
                # 1. Estraiamo i dati dal PDF
                nuovi_pacchi = estrai_dati_pdf(file_caricato)
                
                if not nuovi_pacchi:
                    st.error("Non ho trovato nessuna spedizione valida in questo PDF.")
                else:
                    st.info(f"Trovati {len(nuovi_pacchi)} pacchi. Trasferimento in corso...")
                    
                    # 2. Invio dei dati a Make.com per ogni pacco
                    successi = 0
                    for pacco in nuovi_pacchi:
                        risposta = requests.post(WEBHOOK_URL, json=pacco)
                        if risposta.status_code == 200:
                            successi += 1
                            
                    if successi == len(nuovi_pacchi):
                        st.success(f"✅ Finito! {successi} spedizioni caricate correttamente nel sistema.")
                    else:
                        st.warning(f"⚠️ Operazione completata, ma alcuni pacchi potrebbero non essere stati inviati. Inviati: {successi}/{len(nuovi_pacchi)}.")

            except Exception as e:
                st.error(f"Si è verificato un errore tecnico: {e}")