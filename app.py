import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
import requests

# Controllo disponibilita libreria PDF
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

st.set_page_config(page_title="Handball Tactical & Video Analytics", layout="wide", page_icon="🤾‍♂️")

st.title("🤾‍♂️ Handball Tactical & Video Analytics - Dashboard")
st.caption("Modulo di Video Analisi Integrata, Scouting per Giocatore & Reportistica Avanzata")
st.markdown("---")

# --- SIDEBAR: CARICAMENTO DATI & FILTRI ---
st.sidebar.subheader("📂 Selezione Dati Partita")

uploaded_file = st.sidebar.file_uploader("Upload File CSV (.csv)", type=None)
drive_link = st.sidebar.text_input("Oppure incolla Link Google Drive:")

data_source = None
if uploaded_file is not None:
    data_source = uploaded_file
elif drive_link:
    try:
        drive_link = drive_link.strip()
        if "/d/" in drive_link:
            file_id = drive_link.split("/d/")[1].split("/")[0]
            data_source = f"https://drive.google.com/uc?export=download&confirm=t&id={file_id}"
        else:
            data_source = drive_link
    except Exception as e:
        st.sidebar.error("Formato link Google Drive non valido.")

if data_source is not None:
    try:
        # 1. Caricamento Bytes
        raw_bytes = None
        if isinstance(data_source, str):
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(data_source, headers=headers)
            raw_bytes = response.content
            if b"<!DOCTYPE html>" in raw_bytes or b"<html" in raw_bytes:
                st.error("⚠️ Il link di Google Drive non è accessibile. Imposta la condivisione su 'Chiunque abbia il link'.")
                st.stop()
        else:
            data_source.seek(0)
            raw_bytes = data_source.read()

        try:
            text_content = raw_bytes.decode('utf-8', errors='ignore')
        except:
            text_content = raw_bytes.decode('latin1', errors='ignore')

        lines = text_content.splitlines()

        start_row = 0
        for idx, line in enumerate(lines):
            parts = [p.strip().replace('"', '') for p in line.split(',')]
            if parts[0] in ['Team', 'HOM', 'AWA', 'DEN', 'SLO']:
                if parts[0] == 'Team':
                    start_row = idx + 1
                else:
                    start_row = idx
                break

        # Estrattore automatico Pace
        extracted_pace = 50
        for line in lines[:start_row]:
            parts = [p.strip().replace('"', '') for p in line.split(',')]
            for idx_p, part in enumerate(parts):
                if 'pace' in part.lower():
                    if idx_p + 1 < len(parts) and parts[idx_p + 1].isdigit():
                        extracted_pace = int(parts[idx_p + 1])
                        break

        # 2. Parsing DataFrame
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes), skiprows=start_row, header=None, engine='python', on_bad_lines='skip')
            if df.shape[1] == 1:
                df = pd.read_csv(io.BytesIO(raw_bytes), skiprows=start_row, header=None, sep=';', engine='python', on_bad_lines='skip')
        except:
            df = pd.read_csv(io.BytesIO(raw_bytes), skiprows=start_row, header=None, sep=';', engine='python', on_bad_lines='skip')

        # Mappatura Posizionale Colonne (Foglio csv_type: Cols A-J)
        df['Team'] = df.iloc[:, 0] if df.shape[1] > 0 else None
        df['Result'] = df.iloc[:, 1] if df.shape[1] > 1 else None
        df['Type_Positional'] = df.iloc[:, 2] if df.shape[1] > 2 else None
        df['Side'] = df.iloc[:, 3] if df.shape[1] > 3 else None
        df['Saves_Detail'] = df.iloc[:, 4] if df.shape[1] > 4 else ''
        df['Minute'] = df.iloc[:, 5] if df.shape[1] > 5 else None
        df['Num_Player'] = df.iloc[:, 6] if df.shape[1] > 6 else None
        df['Counter_Detail'] = df.iloc[:, 7] if df.shape[1] > 7 else ''
        df['Situation'] = df.iloc[:, 8] if df.shape[1] > 8 else ''
        df['Video_Link'] = df.iloc[:, 9] if df.shape[1] > 9 else None

        # Minutaggio e Quarti di Gara
        df['Minute_Num'] = pd.to_numeric(df['Minute'], errors='coerce')

        def get_quarter(min_val):
            if pd.isna(min_val):
                return 'Non specificato'
            elif min_val <= 15:
                return "Q1 (0'-15')"
            elif min_val <= 30:
                return "Q2 (15'-30')"
            elif min_val <= 45:
                return "Q3 (30'-45')"
            else:
                return "Q4 (45'-60'+)"

        df['Quarter'] = df['Minute_Num'].apply(get_quarter)

        # Mappature Tattiche
        def process_7m(row):
            val_i = str(row['Situation']).strip() if pd.notna(row['Situation']) else ''
            val_c = str(row['Type_Positional']).strip() if pd.notna(row['Type_Positional']) else ''
            if any(k in val_i.lower() for k in ['7m', 'penalty']) or any(k in val_c.lower() for k in ['7m']):
                return 'Rigore 7m'
            return None

        def get_game_phase(row):
            typ = str(row['Type_Positional']).strip().lower() if pd.notna(row['Type_Positional']) else ''
            if 'counter' in typ or typ.startswith('c '):
                return 'Contropiede / Transizione'
            elif typ in ['wing', 'long', 'break', 'pivot', 'unf']:
                return 'Attacco Posizionale'
            else:
                return 'Altro / Non specificato'

        def get_action_detail(row):
            p_7m = process_7m(row)
            if p_7m:
                return p_7m
            phase = get_game_phase(row)
            if phase == 'Contropiede / Transizione':
                c_detail = str(row['Counter_Detail']).strip() if pd.notna(row['Counter_Detail']) else ''
                return c_detail if c_detail != '' else 'Contropiede Generico'
            elif phase == 'Attacco Posizionale':
                p_detail = str(row['Type_Positional']).strip() if pd.notna(row['Type_Positional']) else ''
                return p_detail if p_detail != '' else 'Posizionale Generico'
            return 'Altro'

        def get_detailed_outcome(row):
            res = str(row['Result']).strip().lower() if pd.notna(row['Result']) else ''
            typ = str(row['Type_Positional']).strip().lower() if pd.notna(row['Type_Positional']) else ''
            sav = str(row['Saves_Detail']).strip().lower() if pd.notna(row['Saves_Detail']) else ''
            
            if res == 'goal':
                return 'Goal'
            elif typ == 'unf' or 'turnover' in typ:
                return 'Palla Persa (unF)'
            elif sav == 's' or 'save' in typ or 'save' in res:
                return 'Parata Portiere'
            elif res in ['no goal', 'out', 'miss']:
                return 'Tiro Fuori / Palo'
            else:
                return None

        df['Type_7m'] = df.apply(process_7m, axis=1)
        df['Is_7m'] = df['Type_7m'].notna()
        df['Game_Phase'] = df.apply(get_game_phase, axis=1)
        df['Action_Detail'] = df.apply(get_action_detail, axis=1)
        df['Detailed_Outcome'] = df.apply(get_detailed_outcome, axis=1)

        def clean_sit(s):
            val = str(s).strip() if pd.notna(s) else ''
            return val if val != '' else 'Parità (6v6)'
        df['Tactical_Setup'] = df['Situation'].apply(clean_sit)

        # Filtri Sidebar
        teams = df['Team'].dropna().unique().tolist()
        teams = [t for t in teams if str(t).strip() in ['DEN', 'SLO', 'HOM', 'AWA', 'RIV'] or len(str(t).strip()) == 3]
        if not teams:
            teams = df['Team'].dropna().unique().tolist()

        selected_team = st.sidebar.selectbox("🎯 Seleziona Squadra:", teams)
        team_df = df[df['Team'] == selected_team].copy()

        st.sidebar.markdown("---")
        st.sidebar.subheader("🎛️ Filtri Combinati Tattici & Giocatore")

        # Filtro Giocatore
        players = team_df['Num_Player'].dropna().unique().tolist()
        selected_player = st.sidebar.selectbox("👤 Giocatore / Num Maglia:", ["Tutti i Giocatori"] + [str(p) for p in sorted(players)])

        # Filtro Assetto Tattico
        setups = sorted(team_df['Tactical_Setup'].dropna().unique().tolist())
        selected_setup = st.sidebar.selectbox("⚖️ Assetto Tattico (Situazione):", ["Tutti gli Assetti"] + setups)

        only_7m = st.sidebar.checkbox("🤾‍♂️ Isola Rigori 7 Metri")

        if not only_7m:
            phase_options = ["Tutte le Fasi", "Attacco Posizionale", "Contropiede / Transizione"]
            selected_phase = st.sidebar.radio("⚡ Fase di Gioco:", phase_options)
            
            selected_detail = "Tutti i Tipi"
            if selected_phase in ["Attacco Posizionale", "Contropiede / Transizione"]:
                sub_df = team_df[team_df['Game_Phase'] == selected_phase]
                detail_options = ["Tutti i Tipi"] + sorted(sub_df['Action_Detail'].dropna().unique().tolist())
                st_label = "🚀 Dettaglio Contropiede:" if selected_phase == "Contropiede / Transizione" else "🎯 Dettaglio Posizionale:"
                selected_detail = st.sidebar.selectbox(st_label, detail_options)
        else:
            selected_phase = "Rigori 7 Metri"
            selected_detail = "Tutti i Tipi"

        # Applicazione Filtri
        filtered_df = team_df.copy()

        if selected_player != "Tutti i Giocatori":
            filtered_df = filtered_df[filtered_df['Num_Player'].astype(str) == selected_player]

        if selected_setup != "Tutti gli Assetti":
            filtered_df = filtered_df[filtered_df['Tactical_Setup'] == selected_setup]

        if only_7m:
            filtered_df = filtered_df[filtered_df['Is_7m'] == True]
        elif selected_phase != "Tutte le Fasi":
            filtered_df = filtered_df[filtered_df['Game_Phase'] == selected_phase]
            if selected_detail != "Tutti i Tipi":
                filtered_df = filtered_df[filtered_df['Action_Detail'] == selected_detail]

        # Calcolo KPI
        possessions = st.sidebar.number_input(f"⏱️ Pace Gara ({selected_team}):", min_value=1, value=extracted_pace)

        gol = len(filtered_df[filtered_df['Detailed_Outcome'] == 'Goal'])
        unf = len(filtered_df[filtered_df['Detailed_Outcome'] == 'Palla Persa (unF)'])
        saves = len(filtered_df[filtered_df['Detailed_Outcome'] == 'Parata Portiere'])
        missed = len(filtered_df[filtered_df['Detailed_Outcome'] == 'Tiro Fuori / Palo'])
        tot_azioni_filtrate = len(filtered_df[filtered_df['Detailed_Outcome'].notna()])
        eff_fase = (gol / tot_azioni_filtrate * 100) if tot_azioni_filtrate > 0 else 0.0

        st.subheader(f"📊 KPI Tattici: {selected_team}")
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Pace (Possessi)", possessions)
        k2.metric("Azioni Filtrate", tot_azioni_filtrate)
        k3.metric("Gol Segnati", gol)
        k4.metric("Parate Subite", saves)
        k5.metric("Palle Perse / Fuori", unf + missed)
        k6.metric("Efficienza %", f"{eff_fase:.1f}%")

        st.markdown("---")

        # --- EFFICACIA TEMPORALE & ASSETTI TATTICI ---
        t1, t2 = st.columns(2)

        with t1:
            st.subheader("⏱️ Efficienza Temporale per Quarto di Gara")
            q_order = ["Q1 (0'-15')", "Q2 (15'-30')", "Q3 (30'-45')", "Q4 (45'-60'+)"]
            q_data = []

            for q in q_order:
                q_df = filtered_df[filtered_df['Quarter'] == q]
                q_tot = len(q_df[q_df['Detailed_Outcome'].notna()])
                q_gol = len(q_df[q_df['Detailed_Outcome'] == 'Goal'])
                q_err = len(q_df[q_df['Detailed_Outcome'].isin(['Palla Persa (unF)', 'Tiro Fuori / Palo'])])
                q_eff = (q_gol / q_tot * 100) if q_tot > 0 else 0.0
                q_data.append({"Quarto": q, "Azioni": q_tot, "Gol": q_gol, "Errori": q_err, "Efficienza %": round(q_eff, 1)})

            df_quarter = pd.DataFrame(q_data)

            fig_q = go.Figure()
            fig_q.add_trace(go.Bar(x=df_quarter['Quarto'], y=df_quarter['Gol'], name='Gol', marker_color='#00FF87'))
            fig_q.add_trace(go.Bar(x=df_quarter['Quarto'], y=df_quarter['Errori'], name='Errori / Perse', marker_color='#FF3B30'))
            fig_q.add_trace(go.Scatter(x=df_quarter['Quarto'], y=df_quarter['Efficienza %'], name='Efficienza %', yaxis='y2', mode='lines+markers+text', text=df_quarter['Efficienza %'].astype(str) + '%', textposition='top center', line=dict(color='#00E5FF', width=3)))

            fig_q.update_layout(
                barmode='group',
                yaxis=dict(title='Numero Azioni'),
                yaxis2=dict(title='Efficienza %', overlaying='y', side='right', range=[0, 105]),
                legend=dict(orientation='h', y=1.15),
                margin=dict(l=20, r=20, t=30, b=20)
            )
            st.plotly_chart(fig_q, use_container_width=True)

        with t2:
            st.subheader("⚖️ Efficienza per Assetto Tattico (Situazione)")
            setup_counts = filtered_df.groupby('Tactical_Setup').apply(
                lambda x: pd.Series({
                    'Azioni Totali': len(x[x['Detailed_Outcome'].notna()]),
                    'Gol': len(x[x['Detailed_Outcome'] == 'Goal']),
                    'Errori': len(x[x['Detailed_Outcome'].isin(['Palla Persa (unF)', 'Tiro Fuori / Palo'])]),
                    'Efficienza %': round((len(x[x['Detailed_Outcome'] == 'Goal']) / len(x[x['Detailed_Outcome'].notna()]) * 100), 1) if len(x[x['Detailed_Outcome'].notna()]) > 0 else 0.0
                })
            ).reset_index()

            fig_setup = px.bar(
                setup_counts,
                x='Tactical_Setup',
                y=['Gol', 'Errori'],
                barmode='group',
                color_discrete_map={'Gol': '#00FF87', 'Errori': '#FF3B30'},
                text_auto=True,
                title="Gol vs Errori per Assetto Tattico"
            )
            st.plotly_chart(fig_setup, use_container_width=True)

        st.markdown("---")

        # --- TABELLA SETTORI ---
        st.subheader("📊 Analisi Zonale per Settore di Campo")
        zone_data = []
        for side_key, side_name in [('left', 'Sinistra'), ('center', 'Centro'), ('right', 'Destra')]:
            z_df = filtered_df[filtered_df['Side'].astype(str).str.strip().str.lower() == side_key]
            z_tot = len(z_df[z_df['Detailed_Outcome'].notna()])
            z_gol = len(z_df[z_df['Detailed_Outcome'] == 'Goal'])
            z_parate = len(z_df[z_df['Detailed_Outcome'] == 'Parata Portiere'])
            z_sbagliati = len(z_df[z_df['Detailed_Outcome'] == 'Tiro Fuori / Palo'])
            z_unf = len(z_df[z_df['Detailed_Outcome'] == 'Palla Persa (unF)'])
            z_eff = (z_gol / z_tot * 100) if z_tot > 0 else 0.0

            zone_data.append({
                "Settore Campo": side_name,
                "Azioni Totali": z_tot,
                "Gol": z_gol,
                "Parate Subite": z_parate,
                "Tiri Fuori": z_sbagliati,
                "Palle Perse": z_unf,
                "Efficienza %": f"{z_eff:.1f}%"
            })

        df_zone = pd.DataFrame(zone_data)
        st.dataframe(df_zone, use_container_width=True, hide_index=True)

        st.markdown("---")

        # --- VIDEO PLAYER INTEGRATO E REGISTRO ---
        st.subheader("🎬 Video Tagging Integrato & Log Azioni")

        log_cols = ['Minute', 'Num_Player', 'Team', 'Tactical_Setup', 'Game_Phase', 'Action_Detail', 'Detailed_Outcome', 'Side', 'Video_Link']
        log_df = filtered_df[filtered_df['Detailed_Outcome'].notna()][log_cols].copy()

        st.dataframe(
            log_df,
            column_config={
                "Video_Link": st.column_config.LinkColumn(
                    "Video Clip 🎥",
                    validate="^https://.*",
                    display_text="▶️ Apri Clip Video"
                )
            },
            use_container_width=True,
            hide_index=True
        )

        # Player Video Integrato con Offset -10s / +10s
        st.markdown("#### 📽️ Player Video Clip con Finestra TAG (-10s / +10s)")
        video_rows = log_df[log_df['Video_Link'].notna() & (log_df['Video_Link'] != '')]

        if not video_rows.empty:
            selected_action_idx = st.selectbox(
                "Seleziona l'azione da riprodurre nel player integrato:",
                options=video_rows.index,
                format_func=lambda i: f"Min {video_rows.loc[i, 'Minute']}' | Giocatore #{video_rows.loc[i, 'Num_Player']} | {video_rows.loc[i, 'Action_Detail']} -> {video_rows.loc[i, 'Detailed_Outcome']}"
            )

            sel_row = video_rows.loc[selected_action_idx]
            vid_url = str(sel_row['Video_Link']).strip()
            min_val = sel_row['Minute']

            start_sec = 0
            if pd.notna(min_val):
                try:
                    start_sec = max(0, int(float(min_val) * 60 - 10))
                except:
                    start_sec = 0

            st.info(f"▶️ Riproduzione azione Minuto **{min_val}'** (Inizio Clip: **{start_sec}s** | Finestra TAG -10s)")

            try:
                st.video(vid_url, start_time=start_sec)
            except Exception as vid_err:
                st.warning(f"Impossibile incorporare direttamente il video. [Clicca qui per aprire il link esternamente]({vid_url})")
        else:
            st.info("Nessun link video disponibile per i filtri selezionati.")

        # Export Report PDF
        st.markdown("---")
        st.subheader("📄 Reportistica PDF")

        if HAS_REPORTLAB:
            def generate_pdf():
                buf = io.BytesIO()
                doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
                styles = getSampleStyleSheet()
                story = []

                story.append(Paragraph(f"<b>🤾‍♂️ Handball Tactical Report: {selected_team}</b>", styles['Heading1']))
                story.append(Spacer(1, 12))

                kpi_data = [
                    ["Pace Gara", "Azioni Filtrate", "Gol", "Parate", "Perse/Fuori", "Efficienza %"],
                    [str(possessions), str(tot_azioni_filtrate), str(gol), str(saves), str(unf + missed), f"{eff_fase:.1f}%"]
                ]
                t_kpi = Table(kpi_data, colWidths=[80, 90, 60, 60, 90, 80])
                t_kpi.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
                ]))
                story.append(t_kpi)
                story.append(Spacer(1, 15))

                doc.build(story)
                return buf.getvalue()

            pdf_bytes = generate_pdf()
            st.download_button(
                label="📥 Scarica Report di Gara Completo (PDF)",
                data=pdf_bytes,
                file_name=f"Report_Tattico_{selected_team}.pdf",
                mime="application/pdf"
            )

    except Exception as e:
        st.error(f"Errore durante l'elaborazione dei dati: {e}")
else:
    st.info("👆 Carica un file CSV o incolla il link di Google Drive per lanciare la video analisi.")
