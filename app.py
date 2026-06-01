import streamlit as st
import pdfplumber
import pandas as pd
import re
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
        # INSERISCI QUI IL NOME ESATTO DEL TUO FILE GOOGLE E DEL FOGLIO
        foglio = client.open("Logistica Tracking").worksheet("Spedizioni") 
        return foglio
    except Exception as e:
        st.error(f"Errore di connessione a Google Fogli: {e}")
        return None

# --- GENERATORE ID UNIVOCO (HASH) ---
def genera_id(destinatario, ddt):
    stringa_base = f"{destinatario.upper()}-{ddt.upper()}"
    codice_univoco = hashlib.md5(stringa_base.encode()).hexdigest()[:8].upper()
    return codice_univoco

# --- FUNZIONE CHIRURGICA DEFINITIVA (PULIZIA TOTALE) ---
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
                                    match = re.search(r'([A-Za-z0-9\s\.\&\-\'/]+?)\s+\d+\s+\d{1,3}(?:\.\d{3})*,\d+', riga)
                                    if match:
                                        testo_grezzo = match.group(1).strip()
                                        testo_grezzo = re.sub(r'^\s*(?:DAP|PF)\b', '', testo_grezzo, flags=re.IGNORECASE).strip()
                                        split_societa = re.split(r'(?i)\b(?:SRL|S\.R\.L\.|SPA|S\.P\.A\.|SNC|S\.N\.C\.)\b', testo_grezzo)
                                        pezzi_validi = [p.strip() for p in split_societa if p.strip()]
                                        if len(pezzi_validi) >= 2:
                                            destinatario = pezzi_validi[-1]
                                        elif len(pezzi_validi) == 1:
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

                            # 3. INDIRIZZO PULITO (Anti-Spazzatura + Calamita + Vaticano)
                            blocco_testo = " ".join([righe[i+j].strip() for j in range(1, 5) if i+j < len(righe)])
                            
                            # Fase 1: Lavaggio (Rimuove telefoni, P.IVA, Corrispondente e scritte inutili)
                            blocco_pulito = re.sub(r'\b\d{9,10}\b', '', blocco_testo)
                            blocco_pulito = re.sub(r'(?i)\b(TEL|CELL|TELEFONO|P\.IVA|PIVA|C\.F\.)\b', '', blocco_pulito)
                            # <-- ECCO LA REGOLA CHE CANCELLA IL CORRISPONDENTE E GLI IMBALLI -->
                            blocco_pulito = re.sub(r'(?i)Corrispondente\s*(?:/|\\)?\s*Distributore', '', blocco_pulito)
                            blocco_pulito = re.sub(r'(?i)\bCorrispondente\b', '', blocco_pulito)
                            blocco_pulito = re.sub(r'(?i)Imballi(?:/Packages)?\s*[:\.]?', '', blocco_pulito)
                            
                            indirizzo = "INDIRIZZO NON TROVATO"
                            blocco_upper = blocco_pulito.upper()
                            
                            # Fase 2: Calamita
                            if "VATICANO" in blocco_upper or "VATICANA" in blocco_upper:
                                match_vat = re.search(r'(?i)([A-Za-z0-9\s]+?CITT[AÀ\']\s+DEL\s+VATICANO\s*(?:VA)?)', blocco_pulito)
                                if match_vat:
                                    indirizzo_grezzo = match_vat.group(1).strip()
                                    indirizzo = re.sub(r'(?i)^(SPED|DEST|CORRISPONDENTE|IMBALLI).*?\s+', '', indirizzo_grezzo).strip()
                            else:
                                # A. Cerchiamo il CAP e la Città del Destinatario (l'ultimo in fondo a destra)
                                citta_destinatario = ""
                                matches_citta = re.findall(r'\d{5}\s+[A-Za-z\s\']+[A-Z]{2}(?:\s*IT)?', blocco_pulito)
                                if matches_citta:
                                    citta_destinatario = matches_citta[-1].strip()
                                
                                # B. Cerchiamo la Via
                                match_via = re.search(r'(?i)(?:VIA|VIALE|V\.LE|PIAZZA|P\.ZZA|P\.LE|STRADA|CORSO|C\.SO|LOC\.|Z\.I\.)\s+[A-Za-z0-9\s\.\,\-\'/]+', blocco_pulito)
                                via_destinatario = ""
                                if match_via:
                                    via_sporca = match_via.group(0)
                                    # Tagliamo via tutto quello che c'è dopo il primo CAP trovato (elimina la città del mittente)
                                    via_sporca = re.sub(r'\s*\d{5}\s+.*', '', via_sporca)
                                    
                                    # Cesoia: prendiamo solo l'ultima occorrenza di VIA, PIAZZA ecc.
                                    split_via = re.split(r'(?i)\s+(?=VIA\b|VIALE\b|V\.LE\b|PIAZZA\b|P\.ZZA\b|P\.LE\b|STRADA\b|CORSO\b|C\.SO\b|LOC\.\b|Z\.I\.\b)', " " + via_sporca)
                                    via_destinatario = split_via[-1].strip()
                                
                                # Uniamo i due pezzi puliti
                                if via_destinatario and citta_destinatario:
                                    indirizzo = f"{via_destinatario} {citta_destinatario}".strip()
                                elif citta_destinatario:
                                    indirizzo = citta_destinatario
                                elif via_destinatario:
                                    indirizzo = via_destinatario

                            # 4. DDT (Solo Numeri)
                            ddt_grezzo = ""
                            for j in range(1, 6):
                                if i+j < len(righe):
                                    riga_check = righe[i+j].strip()
                                    if "Note" in riga_check:
                                        ddt_grezzo = re.sub(r'.*Note\s*[:\s]*', '', riga_check).strip()
                                        break 
                            
                            ddt = ddt_grezzo if ddt_grezzo.isdigit() else ""

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
                                "DDT": ""
                            }

    # ==========================================
    # 2. LETTURA CSV (Invariata)
    # ==========================================
    if file_csv is not None:
        df_csv = pd.read_csv(file_csv, sep=';', dtype=str).fillna("")
        for index, row in df_csv.iterrows():
            try:
                destinatario_csv = str(row['RAGIONE SOCIALE DESTINATARIO']).strip()
                
                via_csv = str(row['INDIRIZZO']).strip()
                cap_grezzo = str(row['CAP']).strip()
                localita_csv = str(row['LOCALITA']).strip()
                provincia_csv = str(row['PROVINCIA']).strip()
                
                cap_csv = cap_grezzo.zfill(5) if cap_grezzo else ""
                
                indirizzo_csv = f"{via_csv} {cap_csv} {localita_csv} {provincia_csv}".strip()
                indirizzo_csv = " ".join(indirizzo_csv.split())
                
                peso_csv = str(row['PESO LORDO']).strip()
                ddt_csv_grezzo = str(row['DDT']).strip()
                
                if destinatario_csv == "": continue
                
                ddt_csv = ddt_csv_grezzo if ddt_csv_grezzo.isdigit() else ""
                
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
