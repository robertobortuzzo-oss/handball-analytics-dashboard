import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
import requests

# Check PDF generation library availability
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
st.caption("Integrated Video Tagging, Player Scouting & Advanced Match Performance Engine")
st.markdown("---")

# --- SIDEBAR: DATA LOADING & FILTERS ---
st.sidebar.subheader("📂 Select Match Data")

uploaded_file = st.sidebar.file_uploader("Upload CSV File (.csv)", type=None)
drive_link = st.sidebar.text_input("Or paste Google Drive Link:")

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
        st.sidebar.error("Invalid Google Drive link format.")

if data_source is not None:
    try:
        # 1. Raw Bytes Loading
        raw_bytes = None
        if isinstance(data_source, str):
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(data_source, headers=headers)
            raw_bytes = response.content
            if b"<!DOCTYPE html>" in raw_bytes or b"<html" in raw_bytes:
                st.error("⚠️ Google Drive link is not accessible. Please set sharing permissions to 'Anyone with the link'.")
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

        # Automatic Match Pace Extractor
        extracted_pace = 50
        for line in lines[:start_row]:
            parts = [p.strip().replace('"', '') for p in line.split(',')]
            for idx_p, part in enumerate(parts):
                if 'pace' in part.lower():
                    if idx_p + 1 < len(parts) and parts[idx_p + 1].isdigit():
                        extracted_pace = int(parts[idx_p + 1])
                        break

        # 2. DataFrame Parsing
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes), skiprows=start_row, header=None, engine='python', on_bad_lines='skip')
            if df.shape[1] == 1:
                df = pd.read_csv(io.BytesIO(raw_bytes), skiprows=start_row, header=None, sep=';', engine='python', on_bad_lines='skip')
        except:
            df = pd.read_csv(io.BytesIO(raw_bytes), skiprows=start_row, header=None, sep=';', engine='python', on_bad_lines='skip')

        # Positional Column Mapping (csv_type Sheet: Cols A-J)
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

        # Numeric Minute & Quarter Mapping
        df['Minute_Num'] = pd.to_numeric(df['Minute'], errors='coerce')

        def get_quarter(min_val):
            if pd.isna(min_val):
                return 'Unspecified'
            elif min_val <= 15:
                return "Q1 (0'-15')"
            elif min_val <= 30:
                return "Q2 (15'-30')"
            elif min_val <= 45:
                return "Q3 (30'-45')"
            else:
                return "Q4 (45'-60'+)"

        df['Quarter'] = df['Minute_Num'].apply(get_quarter)

        # Tactical Logic Mappings
        def process_7m(row):
            val_i = str(row['Situation']).strip() if pd.notna(row['Situation']) else ''
            val_c = str(row['Type_Positional']).strip() if pd.notna(row['Type_Positional']) else ''
            if any(k in val_i.lower() for k in ['7m', 'penalty']) or any(k in val_c.lower() for k in ['7m']):
                return '7m Penalty'
            return None

        def get_game_phase(row):
            typ = str(row['Type_Positional']).strip().lower() if pd.notna(row['Type_Positional']) else ''
            if 'counter' in typ or typ.startswith('c '):
                return 'Fast Break / Transition'
            elif typ in ['wing', 'long', 'break', 'pivot', 'unf']:
                return 'Positional Attack'
            else:
                return 'Other / Unspecified'

        def get_action_detail(row):
            p_7m = process_7m(row)
            if p_7m:
                return p_7m
            phase = get_game_phase(row)
            if phase == 'Fast Break / Transition':
                c_detail = str(row['Counter_Detail']).strip() if pd.notna(row['Counter_Detail']) else ''
                return c_detail if c_detail != '' else 'Generic Counter'
            elif phase == 'Positional Attack':
                p_detail = str(row['Type_Positional']).strip() if pd.notna(row['Type_Positional']) else ''
                return p_detail if p_detail != '' else 'Generic Positional'
            return 'Other'

        def get_detailed_outcome(row):
            res = str(row['Result']).strip().lower() if pd.notna(row['Result']) else ''
            typ = str(row['Type_Positional']).strip().lower() if pd.notna(row['Type_Positional']) else ''
            sav = str(row['Saves_Detail']).strip().lower() if pd.notna(row['Saves_Detail']) else ''
            
            if res == 'goal':
                return 'Goal'
            elif typ == 'unf' or 'turnover' in typ:
                return 'Turnover (unF)'
            elif sav == 's' or 'save' in typ or 'save' in res:
                return 'GK Save'
            elif res in ['no goal', 'out', 'miss']:
                return 'Missed / Out'
            else:
                return None

        df['Type_7m'] = df.apply(process_7m, axis=1)
        df['Is_7m'] = df['Type_7m'].notna()
        df['Game_Phase'] = df.apply(get_game_phase, axis=1)
        df['Action_Detail'] = df.apply(get_action_detail, axis=1)
        df['Detailed_Outcome'] = df.apply(get_detailed_outcome, axis=1)

        def clean_sit(s):
            val = str(s).strip() if pd.notna(s) else ''
            return val if val != '' else 'Equal (6v6)'
        df['Tactical_Setup'] = df['Situation'].apply(clean_sit)

        # Sidebar Filters
        teams = df['Team'].dropna().unique().tolist()
        teams = [t for t in teams if str(t).strip() in ['DEN', 'SLO', 'HOM', 'AWA', 'RIV'] or len(str(t).strip()) == 3]
        if not teams:
            teams = df['Team'].dropna().unique().tolist()

        selected_team = st.sidebar.selectbox("🎯 Select Team:", teams)
        team_df = df[df['Team'] == selected_team].copy()

        st.sidebar.markdown("---")
        st.sidebar.subheader("🎛️ Player & Tactical Filters")

        # Player Scouting Filter
        players = team_df['Num_Player'].dropna().unique().tolist()
        selected_player = st.sidebar.selectbox("👤 Player / Jersey Num:", ["All Players"] + [str(p) for p in sorted(players)])

        # Tactical Setup Filter
        setups = sorted(team_df['Tactical_Setup'].dropna().unique().tolist())
        selected_setup = st.sidebar.selectbox("⚖️ Tactical Setup (Situation):", ["All Setups"] + setups)

        only_7m = st.sidebar.checkbox("🤾‍♂️ Isolate 7-Meter Penalty Shots")

        if not only_7m:
            phase_options = ["All Game Phases", "Positional Attack", "Fast Break / Transition"]
            selected_phase = st.sidebar.radio("⚡ Game Phase:", phase_options)
            
            selected_detail = "All Types"
            if selected_phase in ["Positional Attack", "Fast Break / Transition"]:
                sub_df = team_df[team_df['Game_Phase'] == selected_phase]
                detail_options = ["All Types"] + sorted(sub_df['Action_Detail'].dropna().unique().tolist())
                st_label = "🚀 Fast Break Detail:" if selected_phase == "Fast Break / Transition" else "🎯 Positional Detail:"
                selected_detail = st.sidebar.selectbox(st_label, detail_options)
        else:
            selected_phase = "7-Meter Penalties"
            selected_detail = "All Types"

        # Apply Filters
        filtered_df = team_df.copy()

        if selected_player != "All Players":
            filtered_df = filtered_df[filtered_df['Num_Player'].astype(str) == selected_player]

        if selected_setup != "All Setups":
            filtered_df = filtered_df[filtered_df['Tactical_Setup'] == selected_setup]

        if only_7m:
            filtered_df = filtered_df[filtered_df['Is_7m'] == True]
        elif selected_phase != "All Game Phases":
            filtered_df = filtered_df[filtered_df['Game_Phase'] == selected_phase]
            if selected_detail != "All Types":
                filtered_df = filtered_df[filtered_df['Action_Detail'] == selected_detail]

        # Calculate KPIs
        possessions = st.sidebar.number_input(f"⏱️ Match Pace ({selected_team}):", min_value=1, value=extracted_pace)

        gol = len(filtered_df[filtered_df['Detailed_Outcome'] == 'Goal'])
        unf = len(filtered_df[filtered_df['Detailed_Outcome'] == 'Turnover (unF)'])
        saves = len(filtered_df[filtered_df['Detailed_Outcome'] == 'GK Save'])
        missed = len(filtered_df[filtered_df['Detailed_Outcome'] == 'Missed / Out'])
        tot_azioni_filtrate = len(filtered_df[filtered_df['Detailed_Outcome'].notna()])
        eff_fase = (gol / tot_azioni_filtrate * 100) if tot_azioni_filtrate > 0 else 0.0

        st.subheader(f"📊 Tactical KPIs: {selected_team}")
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Match Pace", possessions)
        k2.metric("Filtered Actions", tot_azioni_filtrate)
        k3.metric("Goals Scored", gol)
        k4.metric("GK Saves Faced", saves)
        k5.metric("Turnovers / Misses", unf + missed)
        k6.metric("Efficiency %", f"{eff_fase:.1f}%")

        st.markdown("---")

        # --- TEMPORAL EFFICIENCY & TACTICAL SETUPS ---
        t1, t2 = st.columns(2)

        with t1:
            st.subheader("⏱️ Temporal Efficiency per Match Quarter")
            q_order = ["Q1 (0'-15')", "Q2 (15'-30')", "Q3 (30'-45')", "Q4 (45'-60'+)"]
            q_data = []

            for q in q_order:
                q_df = filtered_df[filtered_df['Quarter'] == q]
                q_tot = len(q_df[q_df['Detailed_Outcome'].notna()])
                q_gol = len(q_df[q_df['Detailed_Outcome'] == 'Goal'])
                q_err = len(q_df[q_df['Detailed_Outcome'].isin(['Turnover (unF)', 'Missed / Out'])])
                q_eff = (q_gol / q_tot * 100) if q_tot > 0 else 0.0
                q_data.append({"Quarter": q, "Actions": q_tot, "Goals": q_gol, "Errors": q_err, "Efficiency %": round(q_eff, 1)})

            df_quarter = pd.DataFrame(q_data)

            fig_q = go.Figure()
            fig_q.add_trace(go.Bar(x=df_quarter['Quarter'], y=df_quarter['Goals'], name='Goals', marker_color='#00FF87'))
            fig_q.add_trace(go.Bar(x=df_quarter['Quarter'], y=df_quarter['Errors'], name='Errors / Turnovers', marker_color='#FF3B30'))
            fig_q.add_trace(go.Scatter(x=df_quarter['Quarter'], y=df_quarter['Efficiency %'], name='Efficiency %', yaxis='y2', mode='lines+markers+text', text=df_quarter['Efficiency %'].astype(str) + '%', textposition='top center', line=dict(color='#00E5FF', width=3)))

            fig_q.update_layout(
                barmode='group',
                yaxis=dict(title='Action Count'),
                yaxis2=dict(title='Efficiency %', overlaying='y', side='right', range=[0, 105]),
                legend=dict(orientation='h', y=1.15),
                margin=dict(l=20, r=20, t=30, b=20)
            )
            st.plotly_chart(fig_q, use_container_width=True)

        with t2:
            st.subheader("⚖️ Efficiency by Tactical Setup (Situation)")
            setup_counts = filtered_df.groupby('Tactical_Setup').apply(
                lambda x: pd.Series({
                    'Total Actions': len(x[x['Detailed_Outcome'].notna()]),
                    'Goals': len(x[x['Detailed_Outcome'] == 'Goal']),
                    'Errors': len(x[x['Detailed_Outcome'].isin(['Turnover (unF)', 'Missed / Out'])]),
                    'Efficiency %': round((len(x[x['Detailed_Outcome'] == 'Goal']) / len(x[x['Detailed_Outcome'].notna()]) * 100), 1) if len(x[x['Detailed_Outcome'].notna()]) > 0 else 0.0
                })
            ).reset_index()

            fig_setup = px.bar(
                setup_counts,
                x='Tactical_Setup',
                y=['Goals', 'Errors'],
                barmode='group',
                color_discrete_map={'Goals': '#00FF87', 'Errors': '#FF3B30'},
                text_auto=True,
                title="Goals vs Errors per Tactical Setup"
            )
            st.plotly_chart(fig_setup, use_container_width=True)

        st.markdown("---")

        # --- SECTOR SUMMARY ---
        st.subheader("📊 Zonal Sector Efficiency Breakdown")
        zone_data = []
        for side_key, side_name in [('left', 'Left'), ('center', 'Center'), ('right', 'Right')]:
            z_df = filtered_df[filtered_df['Side'].astype(str).str.strip().str.lower() == side_key]
            z_tot = len(z_df[z_df['Detailed_Outcome'].notna()])
            z_gol = len(z_df[z_df['Detailed_Outcome'] == 'Goal'])
            z_parate = len(z_df[z_df['Detailed_Outcome'] == 'GK Save'])
            z_sbagliati = len(z_df[z_df['Detailed_Outcome'] == 'Missed / Out'])
            z_unf = len(z_df[z_df['Detailed_Outcome'] == 'Turnover (unF)'])
            z_eff = (z_gol / z_tot * 100) if z_tot > 0 else 0.0

            zone_data.append({
                "Field Sector": side_name,
                "Total Actions": z_tot,
                "Goals": z_gol,
                "GK Saves": z_parate,
                "Shots Out / Post": z_sbagliati,
                "Turnovers (unF)": z_unf,
                "Efficiency %": f"{z_eff:.1f}%"
            })

        df_zone = pd.DataFrame(zone_data)
        st.dataframe(df_zone, use_container_width=True, hide_index=True)

        st.markdown("---")

        # --- INTEGRATED VIDEO & MATCH LOG ---
        st.subheader("🎬 Integrated Video Tagging & Match Log")

        log_cols = ['Minute', 'Num_Player', 'Team', 'Tactical_Setup', 'Game_Phase', 'Action_Detail', 'Detailed_Outcome', 'Side', 'Video_Link']
        log_df = filtered_df[filtered_df['Detailed_Outcome'].notna()][log_cols].copy()

        st.dataframe(
            log_df,
            column_config={
                "Video_Link": st.column_config.LinkColumn(
                    "Video Clip 🎥",
                    validate="^https://.*",
                    display_text="▶️ Open Clip"
                )
            },
            use_container_width=True,
            hide_index=True
        )

        # Embedded Video Clip Player (-10s / +10s Offset)
        st.markdown("#### 📽️ Video Clip Player (-10s TAG Offset Window)")
        video_rows = log_df[log_df['Video_Link'].notna() & (log_df['Video_Link'] != '')]

        if not video_rows.empty:
            selected_action_idx = st.selectbox(
                "Select action to launch embedded video clip:",
                options=video_rows.index,
                format_func=lambda i: f"Min {video_rows.loc[i, 'Minute']}' | Player #{video_rows.loc[i, 'Num_Player']} | {video_rows.loc[i, 'Action_Detail']} -> {video_rows.loc[i, 'Detailed_Outcome']}"
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

            st.info(f"▶️ Playing Action at Minute **{min_val}'** (Offset Start: **{start_sec}s** | -10s Tag Window)")

            try:
                st.video(vid_url, start_time=start_sec)
            except Exception as vid_err:
                st.warning(f"Unable to embed player directly. [Click here to open Video Link externally]({vid_url})")
        else:
            st.info("No video links available in the filtered dataset.")

        # Export PDF Report
        st.markdown("---")
        st.subheader("📄 Export Match Report")

        if HAS_REPORTLAB:
            def generate_pdf():
                buf = io.BytesIO()
                doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
                styles = getSampleStyleSheet()
                story = []

                story.append(Paragraph(f"<b>🤾‍♂️ Handball Tactical Report: {selected_team}</b>", styles['Heading1']))
                story.append(Spacer(1, 12))

                kpi_data = [
                    ["Pace", "Filtered Actions", "Goals", "Saves", "Turnovers/Out", "Efficiency %"],
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
                label="📥 Download Full Match Report (PDF)",
                data=pdf_bytes,
                file_name=f"Tactical_Report_{selected_team}.pdf",
                mime="application/pdf"
            )

    except Exception as e:
        st.error(f"Error processing dashboard data: {e}")
else:
    st.info("👆 Please upload a CSV file or paste a Google Drive link to launch video analytics.")
