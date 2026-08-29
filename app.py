import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Handball Tactical Analytics", layout="wide")

st.title("🤾‍♂️ Handball Tactical Analytics - Dashboard")
st.markdown("---")

# --- SIDEBAR: CARICAMENTO DATI ---
st.sidebar.subheader("📂 Select Match Data")

uploaded_file = st.sidebar.file_uploader("Upload Match CSV File (.csv)", type=None)
drive_link = st.sidebar.text_input("Or paste Google Drive Link:")

data_source = None

if uploaded_file is not None:
    data_source = uploaded_file
elif drive_link:
    try:
        if "/d/" in drive_link:
            file_id = drive_link.split("/d/")[1].split("/")[0]
            data_source = f"https://drive.google.com/uc?export=download&id={file_id}"
        else:
            data_source = drive_link
    except Exception as e:
        st.sidebar.error("Invalid Google Drive link format.")

if data_source is not None:
    try:
        # 1. Estrazione delle righe sia per Upload Locale sia per Google Drive URL
        lines = []
        if isinstance(data_source, str):
            lines_df = pd.read_csv(data_source, header=None, encoding='latin1', on_bad_lines='skip', engine='python')
            lines = [",".join(map(str, row)) for row in lines_df.values]
        else:
            data_source.seek(0)
            lines = [line.decode('utf-8', errors='ignore') for line in data_source.readlines()]

        start_row = 0
        for idx, line in enumerate(lines):
            first_val = line.split(',')[0].strip().replace('"', '')
            if first_val in ['DEN', 'SLO']:
                start_row = idx
                break

        # Estrattore automatico Pace dall'intestazione del foglio
        extracted_pace = 50
        for line in lines[:start_row]:
            parts = [p.strip().replace('"', '') for p in line.split(',')]
            for idx_p, part in enumerate(parts):
                if 'pace' in part.lower():
                    if idx_p + 1 < len(parts) and parts[idx_p + 1].isdigit():
                        extracted_pace = int(parts[idx_p + 1])
                        break

        # 2. Lettura del dataset principale
        if isinstance(data_source, str):
            df = pd.read_csv(data_source, skiprows=start_row, header=None, encoding='latin1', on_bad_lines='skip', engine='python')
        else:
            data_source.seek(0)
            try:
                df = pd.read_csv(data_source, skiprows=start_row, header=None, sep=None, engine='python')
            except:
                data_source.seek(0)
                df = pd.read_csv(data_source, skiprows=start_row, header=None, sep=';')

        # Mapping Colonne
        df.rename(columns={
            0: 'Team', 
            1: 'Result', 
            2: 'Type_Positional',
            3: 'Side', 
            4: 'Saves_Detail',
            7: 'Counter_Detail',
            8: 'Detail_7m'
        }, inplace=True)

        def process_7m(row):
            val_i = str(row['Detail_7m']).strip() if 'Detail_7m' in row and pd.notna(row['Detail_7m']) else ''
            if val_i != '' and any(k in val_i.lower() for k in ['7m', '7m ext attack', '7m dwn attack', '7m 7x6']):
                return val_i
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
                c_detail = str(row['Counter_Detail']).strip() if 'Counter_Detail' in row and pd.notna(row['Counter_Detail']) else ''
                return c_detail if c_detail != '' else 'Generic Counter'
            elif phase == 'Positional Attack':
                p_detail = str(row['Type_Positional']).strip() if pd.notna(row['Type_Positional']) else ''
                return p_detail if p_detail != '' else 'Generic Positional'
            return 'Other'

        def get_detailed_outcome(row):
            res = str(row['Result']).strip().lower() if pd.notna(row['Result']) else ''
            typ = str(row['Type_Positional']).strip().lower() if pd.notna(row['Type_Positional']) else ''
            sav = str(row['Saves_Detail']).strip().lower() if 'Saves_Detail' in row and pd.notna(row['Saves_Detail']) else ''
            
            if res == 'goal':
                return 'Goal'
            elif typ == 'unf' or 'turnover' in typ:
                return 'Turnover (unF)'
            elif sav == 's' or 'save' in typ or 'save' in res:
                return 'GK Save'
            elif res == 'no goal':
                return 'Missed / Out'
            else:
                return None

        df['Type_7m'] = df.apply(process_7m, axis=1)
        df['Is_7m'] = df['Type_7m'].notna()
        df['Game_Phase'] = df.apply(get_game_phase, axis=1)
        df['Action_Detail'] = df.apply(get_action_detail, axis=1)
        df['Detailed_Outcome'] = df.apply(get_detailed_outcome, axis=1)

        # Filtri Sidebar
        teams = df['Team'].dropna().unique().tolist()
        selected_team = st.sidebar.selectbox("🎯 Select Team:", teams)
        
        team_df = df[df['Team'] == selected_team].copy()
        
        st.sidebar.markdown("---")
        only_7m = st.sidebar.checkbox("🤾‍♂️ Isolate 7-Meter Penalty Shots")
        
        if not only_7m:
            phase_options = ["All Game Phases", "Positional Attack", "Fast Break / Transition"]
            selected_phase = st.sidebar.radio("⚡ Filter by Game Phase:", phase_options)
            
            selected_detail = "All Types"
            if selected_phase in ["Positional Attack", "Fast Break / Transition"]:
                sub_df = team_df[team_df['Game_Phase'] == selected_phase]
                detail_options = ["All Types"] + sorted(sub_df['Action_Detail'].dropna().unique().tolist())
                st_label = "🚀 Fast Break Detail (Col H):" if selected_phase == "Fast Break / Transition" else "🎯 Positional Detail (Col C):"
                selected_detail = st.sidebar.selectbox(st_label, detail_options)
        else:
            selected_phase = "7-Meter Penalties"
            selected_detail = "All Types"

        if only_7m:
            filtered_df = team_df[team_df['Is_7m'] == True].copy()
        elif selected_phase == "All Game Phases":
            filtered_df = team_df.copy()
        elif selected_detail == "All Types":
            filtered_df = team_df[team_df['Game_Phase'] == selected_phase].copy()
        else:
            filtered_df = team_df[(team_df['Game_Phase'] == selected_phase) & 
                                  (team_df['Action_Detail'] == selected_detail)].copy()
        
        st.markdown("---")
        
        possessions = st.sidebar.number_input(
            f"⏱️ Total Match Possessions (Pace) for {selected_team}:", 
            min_value=1, 
            value=extracted_pace
        )
        
        gol = len(filtered_df[filtered_df['Detailed_Outcome'] == 'Goal'])
        unf = len(filtered_df[filtered_df['Detailed_Outcome'] == 'Turnover (unF)'])
        saves = len(filtered_df[filtered_df['Detailed_Outcome'] == 'GK Save'])
        missed = len(filtered_df[filtered_df['Detailed_Outcome'] == 'Missed / Out'])
        tot_azioni_filtrate = len(filtered_df[filtered_df['Detailed_Outcome'].notna()])
        
        eff_fase = (gol / tot_azioni_filtrate * 100) if tot_azioni_filtrate > 0 else 0.0
        
        titolo_dashboard = f"📊 Match KPIs for: {selected_team} ("
        if only_7m:
            titolo_dashboard += "7-Meter Penalty Filter"
        else:
            titolo_dashboard += selected_phase
            if selected_phase != "All Game Phases" and selected_detail != "All Types":
                titolo_dashboard += f" - {selected_detail}"
        titolo_dashboard += ")"
        
        st.header(titolo_dashboard)
        
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("Match Pace (Possessions)", possessions)
        col2.metric("Filtered Actions", tot_azioni_filtrate)
        col3.metric("Goals Scored", gol)
        col4.metric("GK Saves", saves)
        col5.metric("Turnovers / Out", unf + missed)
        col6.metric("Efficiency %", f"{eff_fase:.1f}%")
        
        st.markdown("---")
        
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("📈 Outcome Breakdown")
            filtered_outcomes = filtered_df['Detailed_Outcome'].dropna()
            res_counts = filtered_outcomes.value_counts().reset_index()
            res_counts.columns = ['Detailed Outcome', 'Count']
            
            color_map = {
                'Goal': '#00FF87',
                'GK Save': '#FF3B30',
                'Missed / Out': '#FFCC00',
                'Turnover (unF)': '#FF9500'
            }
            
            fig_res = px.bar(
                res_counts, 
                x='Detailed Outcome', 
                y='Count', 
                color='Detailed Outcome', 
                color_discrete_map=color_map,
                text_auto=True
            )
            st.plotly_chart(fig_res, use_container_width=True)
            
        with c2:
            if only_7m:
                st.subheader("🤾‍♂️ 7-Meter Shot Breakdown (Col I)")
                m7_counts = filtered_df['Type_7m'].value_counts().reset_index()
                m7_counts.columns = ['7m Type', 'Count']
                fig_7m = px.bar(m7_counts, x='7m Type', y='Count', color='7m Type', text_auto=True)
                st.plotly_chart(fig_7m, use_container_width=True)
            elif selected_phase == "Fast Break / Transition":
                st.subheader("🚀 Fast Break Types (Col H)")
                counter_df_all = team_df[team_df['Game_Phase'] == 'Fast Break / Transition']
                c_type_counts = counter_df_all['Action_Detail'].value_counts().reset_index()
                c_type_counts.columns = ['Fast Break Type', 'Count']
                fig_counter = px.bar(c_type_counts, x='Fast Break Type', y='Count', color='Fast Break Type', text_auto=True)
                st.plotly_chart(fig_counter, use_container_width=True)
            elif selected_phase == "Positional Attack":
                st.subheader("🎯 Positional Attack Types (Col C)")
                pos_df_all = team_df[team_df['Game_Phase'] == 'Positional Attack']
                p_type_counts = pos_df_all['Action_Detail'].value_counts().reset_index()
                p_type_counts.columns = ['Positional Type', 'Count']
                fig_pos = px.bar(p_type_counts, x='Positional Type', y='Count', color='Positional Type', text_auto=True)
                st.plotly_chart(fig_pos, use_container_width=True)
            else:
                st.subheader("⚡ Game Phase Distribution")
                phase_counts = team_df[team_df['Detailed_Outcome'].notna()]['Game_Phase'].value_counts().reset_index()
                phase_counts.columns = ['Game Phase', 'Count']
                fig_phase = px.pie(phase_counts, values='Count', names='Game Phase', hole=0.4, color_discrete_sequence=['#1F77B4', '#FF7F0E', '#2CA02C'])
                st.plotly_chart(fig_phase, use_container_width=True)

        st.markdown("---")
        
        st.subheader(f"📊 Zonal Tactical Analysis by Sector ({selected_phase})")
        
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

        tot_z_tot = sum(d["Total Actions"] for d in zone_data)
        tot_z_gol = sum(d["Goals"] for d in zone_data)
        tot_z_parate = sum(d["GK Saves"] for d in zone_data)
        tot_z_sbagliati = sum(d["Shots Out / Post"] for d in zone_data)
        tot_z_unf = sum(d["Turnovers (unF)"] for d in zone_data)
        tot_z_eff = (tot_z_gol / tot_z_tot * 100) if tot_z_tot > 0 else 0.0

        zone_data.append({
            "Field Sector": "🔴 OVERALL TOTAL",
            "Total Actions": tot_z_tot,
            "Goals": tot_z_gol,
            "GK Saves": tot_z_parate,
            "Shots Out / Post": tot_z_sbagliati,
            "Turnovers (unF)": tot_z_unf,
            "Efficiency %": f"{tot_z_eff:.1f}%"
        })

        df_zone_summary = pd.DataFrame(zone_data)

        st.dataframe(
            df_zone_summary.style.highlight_max(
                axis=0, 
                subset=['Goals', 'Total Actions'], 
                color='#1e3d2f'
            ),
            use_container_width=True,
            hide_index=True
        )

        st.markdown("---")

        with st.expander("🔍 View Filtered Match Log"):
            st.dataframe(filtered_df[filtered_df['Detailed_Outcome'].notna()][['Team', 'Type_7m', 'Game_Phase', 'Action_Detail', 'Detailed_Outcome', 'Side']], use_container_width=True)
            
    except Exception as e:
        st.error(f"Error reading file: {e}")
else:
    st.info("👆 Please upload a CSV file or paste a Google Drive link to launch analytics.")