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

# --- FUNZIONE CHIRURGICA PER IL PDF (DEFINITIVA) ---
def elabora_dati(file_pdf, file_csv):
    spedizioni = {}

    # ==========================================
    # 1. LETTURA PDF
    # ==========================================
    if file_pdf is not None:
        with pdfplumber.open(file_pdf) as pdf:
            for pagina in pdf.pages:
                testo = pagina.extract_text(layout=True)
                if not testo: continue
                
                righe = testo.split('\n')
                
                for i, riga in enumerate(righe):
                    if re.search(r'(\d{5}/\d{4}/[A-Z]+)', riga):
                        try:
                            # 1. DESTINATARIO
                            pezzi_riga0 = re.split(r'\s{2,}', riga.strip())
                            destinatario = "ERRORE NOME"
                            
                            for idx, pezzo in enumerate(pezzi_riga0):
                                if re.match(r'^\d+\s+\d{1,3}(?:\.\d{3})*,\d+', pezzo) or re.match(r'^\d+$', pezzo):
                                    if idx > 0:
                                        destinatario = pezzi_riga0[idx-1].strip() 
                                    break
                                    
                            if destinatario == "ERRORE NOME":
                                if len(pezzi_riga0) >= 3:
                                    destinatario = pezzi_riga0[-2].strip()
                                else:
                                    # Salvagente Intelligente: Separa al primo SRL/SPA del mittente
                                    match = re.search(r'([A-Za-z0-9\s\.\&\-\'/]+?)\s+\d+\s+\d{1,3}(?:\.\d{3})*,\d+', riga)
                                    if match:
                                        testo_grezzo = match.group(1).strip()
                                        # Elimina le sigle di spedizione iniziali (DAP, PF)
                                        testo_grezzo = re.sub(r'^\s*(?:DAP|PF)\b', '', testo_grezzo, flags=re.IGNORECASE).strip()
                                        
                                        # Taglia la frase usando le sigle aziendali
                                        split_societa = re.split(r'(?i)\b(?:SRL|S\.R\.L\.|SPA|S\.P\.A\.|SNC|S\.N\.C\.)\b', testo_grezzo)
                                        pezzi_validi = [p.strip() for p in split_societa if p.strip()]
                                        
                                        if len(pezzi_validi) >= 2:
                                            # Prende il blocco di testo DOPO la sigla del mittente
                                            destinatario = pezzi_validi[-1]
                                        elif len(pezzi_validi) == 1:
                                            # Ripiego di sicurezza se non ci sono sigle
                                            parole = pezzi_validi[0].split()
                                            destinatario = " ".join(parole[-3:])

                            # 2. PESO LORDO
                            parole_riga = riga.split()
                            peso = "0"
                            if len(parole_riga) >= 6:
                                if re.match(r'^\d{1,3}(?:\.\d{3})*,\d+$|^\d+,\d+$', parole_riga[-5]):
                                    peso = parole_riga[-5]
                                elif re.match(r'^\d{1,3}(?:\.\d{3})*,\d+$|^\d+,\d+$', parole_riga[-6]):
                                    peso = parole_riga[-6]
                                    
                            if peso == "0":
                                tutti_i_decimali = re.findall(r'\b\d{1,3}(?:\.\d{3})*,\d{2,4}\b', riga)
                                if tutti_i_decimali:
                                    peso = tutti_i_decimali[0]

                            # 3. INDIRIZZO PULITO (Anti-Mittente)
                            via = ""
                            if i+1 < len(righe):
                                pezzi_riga1 = re.split(r'\s{2,}', righe[i+1].strip())
                                via_grezza = pezzi_riga1[-1].strip() if pezzi_riga1 else ""
                                
                                split_via = re.split(r'(?i)\s+(?=VIA\b|VIALE\b|V\.LE\b|PIAZZA\b|P\.ZZA\b|P\.LE\b|STRADA\b|CORSO\b|C\.SO\b|LOC\.\b|Z\.I\.\b)', via_grezza)
                                via = split_via[-1].strip() if split_via else via_grezza
                                
                            citta = ""
                            for j in range(1, 4):
                                if i+j < len(righe):
                                    matches_citta = re.findall(r'\d{5}\s+[A-Za-z\s\']+[A-Z]{2}(?:\s*IT)?', righe[i+j])
                                    if matches_citta:
                                        citta = matches_citta[-1].strip()
                                        break
                                        
                            indirizzo = f"{via} {citta}".strip()

                            # 4. DDT
                            ddt = "NON TROVATO"
                            for j in range(1, 6):
                                if i+j < len(righe):
                                    riga_check = righe[i+j].strip()
                                    if "Note" in riga_check:
                                        ddt = re.sub(r'.*Note\s*[:\s]*', '', riga_check).strip()
                                        break 

                            id_univoco = genera_id(destinatario, ddt)
                            spedizioni[id_univoco] = {
                                "ID_Pacco": id_univoco, 
                                "Destinatario": destinatario, 
                                "Indirizzo": indirizzo, 
                                "Peso_Lordo": peso, 
                                "DDT": ddt
                            }
                        except Exception as e:
                            id_emergenza = f"ERRORE-PDF-{i}"
                            spedizioni[id_emergenza] = {
                                "ID_Pacco": id_emergenza, 
                                "Destinatario": "ERRORE LETTURA", 
                                "Indirizzo": str(e), 
                                "Peso_Lordo": "0", 
                                "DDT": "ERRORE"
                            }
    # ==========================================
    # LETTURA CSV (Invariata)
    # ==========================================
    if file_csv is not None:
        df_csv = pd.read_csv(file_csv, sep=';', dtype=str).fillna("")
        for index, row in df_csv.iterrows():
            try:
                # REINSERISCI QUI I NOMI ESATTI DELLE TUE COLONNE CSV
                destinatario_csv = row['RAGIONE SOCIALE DESTINATARIO']
                indirizzo_csv = row['INDIRIZZO']
                peso_csv = row['PESO LORDO']
                ddt_csv = row['DDT']
                
                if destinatario_csv == "": continue
                
                id_univoco_csv = genera_id(destinatario_csv, ddt_csv)
                spedizioni[id_univoco_csv] = {
                    "ID_Pacco": id_univoco_csv, 
                    "Destinatario": destinatario_csv, 
                    "Indirizzo": indirizzo_csv, 
                    "Peso_Lordo": peso_csv, 
                    "DDT": ddt_csv
                }
            except KeyError as e:
                pass

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
