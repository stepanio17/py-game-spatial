import dash
from dash import html, dcc, Input, Output, State, no_update
import dash_leaflet as dl
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import os
import requests
import time
import copy
from geopy.distance import geodesic
from shapely.geometry import Point, shape, box, mapping

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
server = app.server

FILE_NAME = "DataForSpatialGame.xlsx"
EUROPE_GEOJSON_URL = "https://raw.githubusercontent.com/leakyMirror/map-of-europe/master/GeoJSON/europe.geojson"

def get_game_modes():
    if os.path.exists(FILE_NAME):
        try:
            xls = pd.ExcelFile(FILE_NAME)
            return xls.sheet_names
        except:
            return []
    return []

def get_mode_display_name(sheet_name):
    name_lower = sheet_name.lower()
    if "players" in name_lower:
        return "Родины Футбольных Звёзд"
    if "england" in name_lower:
        return "Стадионы Туманного Альбиона"
    if "champions league" in name_lower:
        return "Стадионы Лиги Чемпионов"
    return f"{sheet_name}"

def load_sheet_data(sheet_name):
    try:
        df = pd.read_excel(FILE_NAME, sheet_name=sheet_name)
        if "player" not in sheet_name.lower() and "игрок" not in sheet_name.lower():
            if {'lat', 'lon'}.issubset(df.columns):
                df['lat'] = pd.to_numeric(df['lat'].astype(str).str.replace(',', '.'), errors='coerce')
                df['lon'] = pd.to_numeric(df['lon'].astype(str).str.replace(',', '.'), errors='coerce')
                df = df.dropna(subset=['lat', 'lon'])
        return df
    except:
        return None

def load_europe_geojson():
    try:
        response = requests.get(EUROPE_GEOJSON_URL)
        return response.json()
    except:
        return None

MODES = get_game_modes()
EUROPE_GEOJSON = load_europe_geojson()

def refine_uk_region(lat, lon):
    if lon < -5.4 and lat > 54.0:
        return "Northern Ireland"
    if lat > 55.35:
        return "Scotland"
    if -5.3 <= lon <= -3.05 and 51.35 <= lat <= 53.45:
        return "Wales"
    return "England"

def get_uk_subregion_feature(feature, region_name):
    try:
        uk_shape = shape(feature['geometry'])
        ni_box = box(-11.0, 54.0, -5.4, 55.5)
        scot_box = box(-9.0, 55.35, 2.0, 62.0)
        wales_box = box(-5.3, 51.35, -3.05, 53.45)

        if region_name.lower() == "northern ireland":
            sub_shape = uk_shape.intersection(ni_box)
        elif region_name.lower() == "scotland":
            sub_shape = uk_shape.intersection(scot_box)
        elif region_name.lower() == "wales":
            sub_shape = uk_shape.intersection(wales_box)
        elif region_name.lower() == "england":
            sub_shape = uk_shape.difference(scot_box).difference(ni_box).difference(wales_box)
            sub_shape = uk_shape.difference(scot_box).difference(ni_box).difference(wales_box)
        else:
            return feature

        new_feature = copy.deepcopy(feature)
        new_feature['geometry'] = mapping(sub_shape)
        return new_feature
    except:
        return feature


def save_to_leaderboard(name, score, duration, mode):
    LEADERBOARD_FILE = "leaderboard.csv"
    target_columns = ["Имя", "Режим", "Очки", "Время (сек)"]
    new_row = pd.DataFrame([{"Имя": name, "Режим": mode, "Очки": score, "Время (сек)": duration}])

    if os.path.exists(LEADERBOARD_FILE):
        try:
            leaderboard_df = pd.read_csv(LEADERBOARD_FILE)
            if not all(col in leaderboard_df.columns for col in target_columns):
                leaderboard_df = pd.DataFrame(columns=target_columns)
        except:
            leaderboard_df = pd.DataFrame(columns=target_columns)
        leaderboard_df = pd.concat([leaderboard_df, new_row], ignore_index=True)
    else:
        leaderboard_df = new_row

    leaderboard_df = leaderboard_df[target_columns]
    leaderboard_df = leaderboard_df.sort_values(by=["Очки", "Время (сек)"], ascending=[False, True])
    leaderboard_df.to_csv(LEADERBOARD_FILE, index=False)

def make_leaderboard_table(df, current_name=None, current_score=None, current_time=None):
    header = html.Thead(html.Tr([html.Th(col) for col in df.columns]))
    rows = []

    for idx, row in df.iterrows():
        is_first = (idx == 0)
        is_current_run = False

        if current_name and str(row['Имя']) == str(current_name):
            match_score = (current_score is None or float(row['Очки']) == float(current_score))
            match_time = (current_time is None or abs(float(row['Время (сек)']) - float(current_time)) < 0.1)
            if match_score and match_time:
                is_current_run = True

        row_style = {}
        if is_first:
            row_style = {'backgroundColor': '#FFD700', 'color': '#212529', 'fontWeight': 'bold'}
        elif is_current_run:
            row_style = {'backgroundColor': '#C3E6CB', 'color': '#155724', 'fontWeight': 'bold'}

        rows.append(html.Tr([html.Td(row[col], style=row_style) for col in df.columns]))

    return dbc.Table([header, html.Tbody(rows)], striped=True, bordered=True, hover=True, responsive=True, size="sm")

def build_league_tabs_widget():
    LEAGUES_FILE = "leagues_standings.csv"

    if not os.path.exists(LEAGUES_FILE):
        return html.Div("Файл турнирных таблиц не найден.", className="text-muted text-center py-3")
    try:
        df = pd.read_csv(LEAGUES_FILE, encoding='utf-8', sep=';')
    except:
        return html.Div("Ошибка при чтении файла таблиц.", className="text-muted text-center py-3")

    tabs_children = []
    unique_leagues = df['Лига'].unique()

    for league_name in unique_leagues:
        df_league = df[df['Лига'] == league_name]
        table_rows = []

        for _, t in df_league.iterrows():
            table_rows.append(html.Tr([
                html.Td(t["М"], style={'fontWeight': 'bold', 'padding': '4px 2px'}),
                html.Td(t["Клуб"],
                        style={'textAlign': 'left', 'padding': '4px 2px', 'whiteSpace': 'nowrap', 'overflow': 'hidden',
                               'textOverflow': 'ellipsis'}),
                html.Td(t["И"], style={'padding': '4px 2px'}),
                html.Td(t["В"], style={'padding': '4px 2px', 'color': '#28a745'}),
                html.Td(t["Н"], style={'padding': '4px 2px', 'color': '#6c757d'}),
                html.Td(t["П"], style={'padding': '4px 2px', 'color': '#dc3545'}),
                html.Td(t["О"], style={'fontWeight': 'bold', 'padding': '4px 2px', 'backgroundColor': '#f8f9fa'})
            ]))

        table_element = dbc.Table([
            html.Thead(html.Tr([
                html.Th("М", style={'padding': '4px 2px', 'width': '26px'}),
                html.Th("Клуб", style={'textAlign': 'left', 'padding': '4px 2px'}),
                html.Th("И", style={'padding': '4px 2px', 'width': '26px'}),
                html.Th("В", style={'padding': '4px 2px', 'width': '22px'}),
                html.Th("Н", style={'padding': '4px 2px', 'width': '22px'}),
                html.Th("П", style={'padding': '4px 2px', 'width': '22px'}),
                html.Th("О", style={'padding': '4px 2px', 'width': '32px'})
            ]), style={'backgroundColor': '#eef1f6', 'fontSize': '10px'}),
            html.Tbody(table_rows)
        ], bordered=False, hover=True, size="sm",
            style={'fontSize': '11px', 'textAlign': 'center', 'marginBottom': '0px', 'tableLayout': 'fixed'})

        scroll_container = html.Div(
            table_element,
            style={'maxHeight': '570px', 'overflowY': 'auto', 'marginTop': '5px', 'borderBottom': '1px solid #edf2f7'}
        )

        tabs_children.append(dbc.Tab(
            scroll_container,
            label=league_name,
            tab_id=league_name,
            tab_style={'padding': '4px 6px', 'fontSize': '11px'},
            label_style={'fontSize': '11px', 'color': '#495057'}
        ))

    return dbc.Tabs(
        id="league-tabs-container",
        children=tabs_children,
        active_tab=unique_leagues[0] if len(unique_leagues) > 0 else None
    )

def build_world_cup_widget():
    WC_FILE = "world_cup_matches.xlsx"

    if not os.path.exists(WC_FILE):
        if os.path.exists("world_cup_matches.csv"):
            WC_FILE = "world_cup_matches.csv"
        else:
            return html.Div("Файл матчей ЧМ не найден.", className="text-muted text-center py-3", style={'fontSize': '12px'})

    try:
        if WC_FILE.endswith('.csv'):
            df = pd.read_csv(WC_FILE, encoding='utf-8')
        else:
            try:
                df = pd.read_excel(WC_FILE)
            except:
                df = pd.read_csv(WC_FILE, encoding='utf-8')
    except:
        return html.Div("Ошибка при чтении файла матчей ЧМ.", className="text-muted text-center py-3", style={'fontSize': '12px'})

    df = df.fillna("")
    match_elements = []
    total_rows = len(df)

    if total_rows == 0:
        return html.Div("В расписании пока нет матчей.", className="text-muted text-center py-3", style={'fontSize': '12px'})

    for idx, r in df.iterrows():
        is_last = (idx == total_rows - 1)
        block_class = "pb-1 mb-0" if is_last else "pb-2 mb-2 border-bottom"

        def get_flag_img(flag_code):
            code_clean = str(flag_code).strip().lower()
            if not code_clean:
                return ""
            return html.Img(
                src=f"https://flagcdn.com/w20/{code_clean}.png",
                style={'borderRadius': '2px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.2)', 'verticalAlign': 'middle'}
            )
            return flag_code

        flag1_img = get_flag_img(r['Флаг1'])
        flag2_img = get_flag_img(r['Флаг2'])

        match_elements.append(html.Div([
            html.Small(f"{r['Дата']} | {r['Группа']}", className="text-muted d-block", style={'fontSize': '11px'}),
            html.Div([
                html.Span([f"{r['Команда1']} ", flag1_img], className="fw-bold", style={'display': 'inline-flex', 'alignItems': 'center', 'gap': '6px'}),
                html.Span(" — ", className="text-muted mx-2"),
                html.Span([flag2_img, f" {r['Команда2']}"], className="fw-bold", style={'display': 'inline-flex', 'alignItems': 'center', 'gap': '6px'})
            ], style={'fontSize': '13px', 'marginTop': '2px', 'display': 'flex', 'alignItems': 'center'})
        ], className=block_class))

    return html.Div(match_elements, style={'maxHeight': '570px', 'overflowY': 'auto', 'marginTop': '5px', 'paddingRight': '5px'})

# ==============================================================================
# LAYOUT
# ==============================================================================
app.layout = dbc.Container([
    dcc.Store(id='game-state',
              data={'round': 1, 'score': 0, 'answered': False, 'max_rounds': 10, 'player_name': 'Игрок',
                    'active_mode': '', 'is_player': False, 'history': []}),
    dcc.Store(id='game-data'),
    dcc.Store(id='click-coords'),

    # СТАРТОВЫЙ ЭКРАН
    html.Div(id='start-screen', style={'padding': '50px 10px', 'maxWidth': '1300px', 'margin': '0 auto'}, children=[
        html.H1("⚽ Football GeoGuesser", className="text-center mb-5",
                style={'fontWeight': 'bold', 'color': '#1a202c'}),

        dbc.Row([
            # ЛЕВАЯ ПАНЕЛЬ: Таблицы чемпионатов из leagues_standings.csv
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("🏆 Таблицы чемпионатов", className="fw-bold text-dark mb-3",
                                style={'letterSpacing': '0.5px'}),
                        build_league_tabs_widget()
                    ], style={'padding': '15px 10px'})
                ], style={'boxShadow': '0 4px 15px rgba(0,0,0,0.04)', 'borderRadius': '15px', 'border': 'none',
                          'overflow': 'hidden'})
            ], width=3),

            # ЦЕНТРАЛЬНАЯ ПАНЕЛЬ: Главное меню настроек матча
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Label("👤 Ваше имя перед стартом:", className="fw-bold mb-2"),
                        dbc.Input(id='player-name-input', value="Игрок", type="text", className="mb-4"),

                        html.Label("🗺️ Выберите режим игры:", className="fw-bold mb-2"),
                        dbc.RadioItems(
                            id='mode-selector',
                            options=[{'label': get_mode_display_name(m), 'value': m} for m in MODES],
                            value=MODES[0] if MODES else None,
                            className="mb-4"
                        ),
                        html.Div(id='rules-block', className="mb-4"),

                        html.Div(id='start-leaderboard-container', className="mb-4"),

                        html.Div(
                            dbc.Button("🚀 Начать игру", id='start-btn', color="primary", size="lg",
                                       style={'padding': '10px 40px'}),
                            className="text-center"
                        )
                    ])
                ], style={'boxShadow': '0 4px 15px rgba(0,0,0,0.05)', 'borderRadius': '15px'})
            ], width=6),

            # ПРАВАЯ ПАНЕЛЬ: Афиша матчей ЧМ из Excel
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("📅 ЧМ: Главные матчи", className="fw-bold text-dark mb-3",
                                style={'letterSpacing': '0.5px'}),
                        build_world_cup_widget()
                    ], style={'padding': '15px 15px'})
                ], style={'boxShadow': '0 4px 15px rgba(0,0,0,0.04)', 'borderRadius': '15px', 'border': 'none'})
            ], width=3)
        ])
    ]),

    html.Div(id='game-container'),

    html.Div(id='end-screen', style={'display': 'none', 'padding': '50px', 'maxWidth': '900px', 'margin': '0 auto'},
             children=[
                 html.H1("🏆 Игра окончена!", className="text-success text-center mb-4", style={'fontWeight': 'bold'}),
                 dbc.Row([
                     dbc.Col(dbc.Alert(id='final-score-report', color="success",
                                       className="d-flex align-items-center justify-content-center text-center",
                                       style={'fontSize': '20px', 'height': '100%'}), width=6),
                     dbc.Col(dbc.Alert(id='final-time-report', color="info",
                                       className="d-flex align-items-center justify-content-center text-center",
                                       style={'fontSize': '20px', 'height': '100%'}), width=6),
                 ], className="mb-4"),

                 html.Div(id='end-charts-container', className="mb-4"),

                 html.H3("🏅 Таблица лидеров режима", className="mb-3", style={'fontWeight': 'bold'}),
                 html.Div(id='leaderboard-table-container', className="mb-4"),

                 html.Div(
                     dbc.Button("В главное меню 🔄", id='restart-btn', color="secondary", size="lg"),
                     className="text-center"
                 )
             ])
], fluid=True, style={'backgroundColor': '#f4f6f9', 'minHeight': '100vh', 'color': '#212529'})

# ==============================================================================
# CALLBACKS
# ==============================================================================

@app.callback(
    Output('rules-block', 'children'),
    Output('start-leaderboard-container', 'children'),  # Добавили новый выход
    Input('mode-selector', 'value'),
    Input('restart-btn', 'n_clicks')
)
def update_rules_and_main_leaderboard(selected_mode, restart_clicks):
    if not selected_mode:
        return "", ""

    if "player" in selected_mode.lower() or "игрок" in selected_mode.lower():
        rules_alert = dbc.Alert([
            html.H5("📋 Правила: Родина футболистов", className="alert-heading"),
            html.P("Перед вами фотографии известных игроков. Твоя задача — угадать страну рождения футболиста и выбрать её на карте Европы. За каждый верный ответ вы получаете 1 балл. Всего в игре 20 раундов.", className="mb-0")
        ], color="info", className="mb-3 text-center")
    else:
        rules_alert = dbc.Alert([
            html.H5("📋 Правила: Где Играем?", className="alert-heading"),
            html.P("Тебе даны эмблема и название стадиона футбольного клуба. Твоя задача - кликнуть по карте, как можно ближе к стадиону клуба! Максимум 10000 очков. Всего: 10 раундов.", className="mb-0") # ── ИСПРАВЛЕНО
        ], color="info", className="mb-3 text-center")

    table_element = html.Div("В этом режиме пока нет рекордов. Будь первым!",
                             className="text-muted text-center style={'fontSize': '14px'}")
    if os.path.exists("leaderboard.csv"):
        try:
            lead_df = pd.read_csv("leaderboard.csv")
            filtered = lead_df[lead_df["Режим"] == selected_mode].reset_index(drop=True)
            if not filtered.empty:
                filtered = filtered.drop(columns=["Regime", "Режим"], errors='ignore')
                filtered.insert(0, 'Место', filtered.index + 1)
                table_element = html.Div([
                    html.H5("🏅 Топ-10 лучших результатов режима:", className="fw-bold mt-2 mb-2",
                            style={'fontSize': '16px'}),
                    make_leaderboard_table(filtered.head(10))
                ])
        except:
            pass

    return rules_alert, table_element


@app.callback(
    Output('start-screen', 'style'),
    Output('game-container', 'children'),
    Output('game-data', 'data'),
    Output('game-state', 'data'),
    Input('start-btn', 'n_clicks'),
    State('player-name-input', 'value'),
    State('mode-selector', 'value'),
    prevent_initial_call=True
)
def start_game_session(n_clicks, p_name, selected_mode):
    if not n_clicks or not selected_mode:
        return no_update, no_update, no_update, no_update

    df = load_sheet_data(selected_mode)
    if df is None or df.empty:
        return no_update, no_update, no_update, no_update

    is_player = "player" in selected_mode.lower() or "игрок" in selected_mode.lower()
    max_r = 20 if is_player else 10

    sampled_records = df.sample(min(max_r, len(df))).to_dict(orient='records')
    current_item = sampled_records[0]

    if is_player:
        top_row_html = html.H5(f"👤 Футболист: {current_item['player']}", id='info-stadium', className="fw-bold mb-1")
        bottom_row_html = html.P("", id='info-club', className="text-muted")

        media_html = html.Div("Фото отсутствует", className="text-muted my-3")
        for ext in ['.png', '.jpg', '.jpeg', '.webp', '.PNG', '.JPG', '.WEBP']:
            path = f"assets/players/{current_item['player']}{ext}"
            if os.path.exists(path):
                media_html = html.Img(src=f"/assets/players/{current_item['player']}{ext}",
                                      style={'width': '100%', 'maxWidth': '280px', 'borderRadius': '12px',
                                             'boxShadow': '0 4px 12px rgba(0,0,0,0.15)'})
                break
        map_center, map_zoom = [50.0, 10.0], 5
    else:
        top_row_html = html.H5(f"⚽ Клуб: {current_item['club']}", id='info-stadium', className="fw-bold mb-1")
        bottom_row_html = html.P(f"🏟️ Стадион: {current_item['stadium']}", id='info-club', className="text-white-50")
        media_html = html.Div("Эмблема отсутствует", className="text-muted my-3")
        for ext in ['.png', '.jpg', '.jpeg', '.webp', '.PNG', '.JPG', '.WEBP']:
            path = f"assets/logos/{current_item['club']}{ext}"
            if os.path.exists(path):
                media_html = html.Img(src=f"/assets/logos/{current_item['club']}{ext}",
                                      style={'width': '100%', 'maxWidth': '280px', 'borderRadius': '12px',
                                             'boxShadow': '0 4px 12px rgba(0,0,0,0.15)'})
                break

        if "eng" in selected_mode.lower() or "англ" in selected_mode.lower():
            map_center, map_zoom = [53.0, -1.5], 7
        else:
            map_center, map_zoom = [50.0, 10.0], 5

    init_state = {
        'round': 1, 'score': 0, 'answered': False,
        'max_rounds': len(sampled_records), 'player_name': p_name,
        'active_mode': selected_mode, 'start_time': time.time(), 'is_player': is_player, 'history': []
    }

    game_layout = dbc.Row([
        dbc.Col([
            html.H5(f"Игрок: {p_name}", className="text-secondary mb-1", style={'fontSize': '15px'}),
            html.H3(f"Раунд 1 из {len(sampled_records)}", id='round-indicator', className="mb-2 text-dark",
                    style={'fontWeight': 'bold'}),
            html.H4("Общий счет: 0", id='score-indicator', className="text-success mb-4", style={'fontWeight': 'bold'}),
            html.Hr(style={'borderColor': '#e2e8f0'}),
            html.Div(id='stadium-info-block', children=[top_row_html, bottom_row_html,
                                                        html.Div(media_html, id='logo-container', className="my-3",
                                                                 style={'textAlign': 'center'})]),
            html.Div(id='feedback-block', className="mt-3"),
            dbc.Button("🚀 Подтвердить выбор", id='confirm-btn', color="primary", disabled=True, className="w-100 mt-3",
                       style={'fontWeight': 'bold', 'borderRadius': '8px'}),
            dbc.Button("Следующий раунд ➡️", id='next-btn', color="success",
                       style={'display': 'none', 'fontWeight': 'bold', 'borderRadius': '8px'}, className="w-100 mt-2")
        ], width=4, style={'background': '#ffffff', 'padding': '25px', 'borderRadius': '16px',
                           'boxShadow': '0 4px 20px rgba(0,0,0,0.06)'}),

        dbc.Col([
            dl.MapContainer(id="geo-map", center=map_center, zoom=map_zoom, children=[
                dl.TileLayer(url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"),
                dl.LayerGroup(id="map-elements-layer")
            ], style={'width': '100%', 'height': '720px', 'borderRadius': '16px',
                      'boxShadow': '0 4px 20px rgba(0,0,0,0.06)'})
        ], width=8)
    ], style={'padding': '20px'})

    return {'display': 'none'}, game_layout, sampled_records, init_state


@app.callback(
    Output('map-elements-layer', 'children', allow_duplicate=True),
    Output('click-coords', 'data'),
    Output('confirm-btn', 'disabled'),
    Input('geo-map', 'clickData'),
    State('game-state', 'data'),
    prevent_initial_call=True
)
def handle_map_click(click_data, state):
    if state['answered'] or not click_data or 'latlng' not in click_data:
        return no_update, no_update, no_update

    latlng = click_data['latlng']
    click_lat_lng = [latlng['lat'], latlng['lng']]

    orange_icon = {
        "iconUrl": "data:image/svg+xml;utf8,<svg width='32' height='44' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'><path d='M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-12-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z' fill='%23FFA500' stroke='%231A1A1A' stroke-width='0.8'/></svg>",
        "iconSize": [32, 44],
        "iconAnchor": [16, 44]
    }
    return [dl.Marker(position=click_lat_lng, icon=orange_icon)], click_lat_lng, False


@app.callback(
    Output('map-elements-layer', 'children'),
    Output('geo-map', 'viewport'),
    Output('feedback-block', 'children'),
    Output('game-state', 'data', allow_duplicate=True),
    Output('confirm-btn', 'style'),
    Output('next-btn', 'style'),
    Input('confirm-btn', 'n_clicks'),
    State('click-coords', 'data'),
    State('game-data', 'data'),
    State('game-state', 'data'),
    prevent_initial_call=True
)
def confirm_guess(n_clicks, u_coords, game_data, state):
    if not n_clicks or not u_coords:
        return no_update, no_update, no_update, no_update, no_update, no_update

    current_item = game_data[state['round'] - 1]
    is_player = state.get('is_player', False)

    elements = []

    if is_player:
        user_lat, user_lon = u_coords[0], u_coords[1]
        click_point = Point(user_lon, user_lat)
        base_clicked_country = "Undefined"
        selected_feature = None
        correct_country_feature = None

        if EUROPE_GEOJSON:
            for feature in EUROPE_GEOJSON['features']:
                polygon_shape = shape(feature['geometry'])
                if polygon_shape.contains(click_point):
                    base_clicked_country = feature['properties'].get('NAME',
                                                                     feature['properties'].get('name', 'Unknown'))
                    selected_feature = feature
                    break

        final_clicked_country = refine_uk_region(user_lat,
                                                 user_lon) if base_clicked_country == "United Kingdom" else base_clicked_country

        if final_clicked_country in ["Undefined", "Unknown"]:
            feedback = dbc.Alert(
                "📍 Вы кликнули не по стране из Европы! Прицельтесь точнее и нажимайте строго по сухопутной территории стран",
                color="warning", className="fw-bold")
            return no_update, no_update, feedback, state, {'display': 'block'}, {'display': 'none'}

        correct_country_name = current_item['country']
        search_target = "United Kingdom" if correct_country_name.lower() in ["england", "scotland", "wales",
                                                                             "northern ireland"] else correct_country_name

        if EUROPE_GEOJSON:
            for feature in EUROPE_GEOJSON['features']:
                f_name = feature['properties'].get('NAME', feature['properties'].get('name', ''))
                if f_name.lower() == search_target.lower():
                    correct_country_feature = feature
                    break

        is_correct = final_clicked_country.lower() == correct_country_name.lower()
        points = 1 if is_correct else 0
        state['score'] += points

        if correct_country_feature:
            feat = get_uk_subregion_feature(correct_country_feature, correct_country_name) if correct_country_feature[
                                                                                                  'properties'].get(
                'NAME', '').lower() == "united kingdom" else correct_country_feature
            elements.append(dl.GeoJSON(data=feat, style=dict(fillColor="green", color="green", fillOpacity=0.4)))

        if points == 0 and selected_feature:
            feat = get_uk_subregion_feature(selected_feature, final_clicked_country) if selected_feature[
                                                                                            'properties'].get('NAME',
                                                                                                              '').lower() == "united kingdom" else selected_feature
            elements.append(dl.GeoJSON(data=feat, style=dict(fillColor="red", color="red", fillOpacity=0.4)))

        red_icon = {
            "iconUrl": "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png",
            "iconSize": [25, 41], "iconAnchor": [12, 41]}
        elements.append(dl.Marker(position=u_coords, icon=red_icon))

        feedback = dbc.Alert(
            f"🎉 Правильно! Это {correct_country_name}" if is_correct else f"❌ Неверно! Вы выбрали: {final_clicked_country}. Правильно: {correct_country_name}",
            color="success" if is_correct else "danger")
        state['history'].append({'Item': current_item['player'], 'Status': "✅ Правильно" if is_correct else "❌ Ошибка"})

        if correct_country_feature:
            try:
                country_shape = shape(correct_country_feature['geometry'])
                minx, miny, maxx, maxy = country_shape.bounds

                user_lat_clamped = max(miny - 6.0, min(maxy + 6.0, u_coords[0]))
                user_lon_clamped = max(minx - 8.0, min(maxx + 8.0, u_coords[1]))

                min_lat = min(miny, user_lat_clamped)
                min_lon = min(minx, user_lon_clamped)
                max_lat = max(maxy, user_lat_clamped)
                max_lon = max(maxx, user_lon_clamped)

                lat_diff = max(max_lat - min_lat, 3.0)
                lon_diff = max(max_lon - min_lon, 3.0)

                lat_center = (min_lat + max_lat) / 2
                lon_center = (min_lon + max_lon) / 2

                padded_bounds = [
                    [lat_center - lat_diff * 0.65, lon_center - lon_diff * 0.65],
                    [lat_center + lat_diff * 0.65, lon_center + lon_diff * 0.65]
                ]
            except:
                padded_bounds = [[u_coords[0] - 3, u_coords[1] - 3], [u_coords[0] + 3, u_coords[1] + 3]]
        else:
            padded_bounds = [[u_coords[0] - 3, u_coords[1] - 3], [u_coords[0] + 3, u_coords[1] + 3]]

    else:
        a_coords = [current_item['lat'], current_item['lon']]
        distance = geodesic(u_coords, a_coords).km

        if "eng" in state['active_mode'].lower() or "англ" in state['active_mode'].lower():
            if distance < 1.0:
                points = 1000
            else:
                points = max(0, int(1000 - (distance * 4)))
        else:
            if distance < 5.0:
                points = 1000
            else:
                points = max(0, int(1000 - distance))
        state['score'] += points

        red_icon = {
            "iconUrl": "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png",
            "iconSize": [25, 41], "iconAnchor": [12, 41]}
        green_icon = {
            "iconUrl": "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-green.png",
            "iconSize": [25, 41], "iconAnchor": [12, 41]}

        elements = [
            dl.Marker(position=u_coords, icon=red_icon, children=dl.Tooltip("Ваш выбор")),
            dl.Marker(position=a_coords, icon=green_icon, children=dl.Tooltip(current_item['stadium'])),
            dl.Polyline(positions=[u_coords, a_coords], color="blue", weight=3)
        ]

        state['history'].append({
            'Item': current_item['club'], 'Distance': round(distance, 1),
            'u_lat': u_coords[0], 'u_lon': u_coords[1],
            'a_lat': a_coords[0], 'a_lon': a_coords[1]
        })

        lat_center, lon_center = (u_coords[0] + a_coords[0]) / 2, (u_coords[1] + a_coords[1]) / 2

        lat_diff = abs(u_coords[0] - a_coords[0])
        lon_diff = abs(u_coords[1] - a_coords[1])

        lat_margin = max(lat_diff, 0.003)
        lon_margin = max(lon_diff, 0.005)

        padded_bounds = [
            [lat_center - lat_margin, lon_center - lon_margin],
            [lat_center + lat_margin, lon_center + lon_margin]
        ]

        feedback = html.Div([
            dbc.Alert(f"Точный ответ: {current_item['city']}", color="info", className="mb-1"),
            dbc.Alert(f"Ошибка: {distance:.1f} км (+{points} очков)", color="warning" if points < 600 else "success")
        ])

    state['answered'] = True
    return elements, dict(bounds=padded_bounds), feedback, state, {'display': 'none'}, {'display': 'block'}

@app.callback(
    Output('round-indicator', 'children'),
    Output('score-indicator', 'children'),
    Output('info-stadium', 'children'),
    Output('info-club', 'children'),
    Output('logo-container', 'children'),
    Output('feedback-block', 'children', allow_duplicate=True),
    Output('confirm-btn', 'style', allow_duplicate=True),
    Output('next-btn', 'style', allow_duplicate=True),
    Output('confirm-btn', 'disabled', allow_duplicate=True),
    Output('map-elements-layer', 'children', allow_duplicate=True),
    Output('geo-map', 'viewport', allow_duplicate=True),
    Output('game-container', 'children', allow_duplicate=True),
    Output('end-screen', 'style'),
    Output('final-score-report', 'children'),
    Output('final-time-report', 'children'),
    Output('leaderboard-table-container', 'children'),
    Output('end-charts-container', 'children'),
    Output('game-state', 'data', allow_duplicate=True),
    Input('next-btn', 'n_clicks'),
    State('game-data', 'data'),
    State('game-state', 'data'),
    prevent_initial_call=True
)
def next_round_or_end(n_clicks, game_data, state):
    if not n_clicks or not game_data:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

    is_player = state.get('is_player', False)

    if state['round'] >= state['max_rounds']:
        if state.get('saved', False):
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, None, None, {
                'display': 'block'}, no_update, no_update, no_update, no_update, state

        total_time = round(time.time() - state['start_time'], 1)
        save_to_leaderboard(state['player_name'], state['score'], total_time, state['active_mode'])
        state['saved'] = True

        table_element = html.Div("Рекордов пока нет.", className="text-muted")
        if os.path.exists("leaderboard.csv"):
            lead_df = pd.read_csv("leaderboard.csv")
            filtered = lead_df[lead_df["Режим"] == state['active_mode']].reset_index(drop=True)
            if not filtered.empty:
                filtered = filtered.drop(columns=["Regime", "Режим"], errors='ignore')
                filtered.insert(0, 'Место', filtered.index + 1)
                table_element = make_leaderboard_table(
                    filtered.head(10),
                    current_name=state['player_name'],
                    current_score=state['score'],
                    current_time=total_time
                )

        chart_element = html.Div()
        if state.get('history') and not is_player:
            df_hist = pd.DataFrame(state['history'])

            fig = px.bar(
                df_hist, x='Item', y='Distance', title='Величина промаха по раундам (км)',
                labels={'Item': 'Клуб / Стадион', 'Distance': 'Промах (км)'}
            )
            fig.update_traces(marker_color='#007bff')
            fig.update_layout(xaxis_title="Команда", yaxis_title="Расстояние (км)", template="plotly_white")

            map_elements = []
            red_icon = {
                "iconUrl": "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png",
                "iconSize": [25, 41], "iconAnchor": [12, 41]}
            green_icon = {
                "iconUrl": "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-green.png",
                "iconSize": [25, 41], "iconAnchor": [12, 41]}

            for h in state['history']:
                map_elements.append(dl.Marker(position=[h['u_lat'], h['u_lon']], icon=red_icon,
                                              children=dl.Tooltip(f"Выбор: {h['Item']}")))
                map_elements.append(dl.Marker(position=[h['a_lat'], h['a_lon']], icon=green_icon,
                                              children=dl.Tooltip(f"Стадион: {h['Item']}")))
                map_elements.append(
                    dl.Polyline(positions=[[h['u_lat'], h['u_lon']], [h['a_lat'], h['a_lon']]], color="blue", weight=2))

            if "eng" in state['active_mode'].lower() or "англ" in state['active_mode'].lower():
                f_center, f_zoom = [53.0, -1.5], 7
            else:
                f_center, f_zoom = [48.0, 10.0], 5

            final_map_layout = html.Div([
                html.H5("🗺️ Карта всех ваших попыток в этой сессии:", className="fw-bold mb-2",
                        style={'fontSize': '16px'}),
                dl.MapContainer(center=f_center, zoom=f_zoom, children=[
                    dl.TileLayer(url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"),
                    dl.LayerGroup(children=map_elements)
                ], style={'width': '100%', 'height': '450px', 'borderRadius': '12px',
                          'boxShadow': '0 4px 12px rgba(0,0,0,0.1)'})
            ])

            chart_element = dbc.Row([
                dbc.Col(html.Div([
                    html.H5("📊 Аналитика величины промахов:", className="fw-bold mb-2", style={'fontSize': '16px'}),
                    dcc.Graph(figure=fig)
                ]), width=6),
                dbc.Col(final_map_layout, width=6)
            ], className="mt-4 align-items-stretch")

        final_score = state['score']
        if is_player:
            if final_score < 8:
                comment = "Нуууууу... не переживай, у меня есть dvd-диски с хоккейными матчами, хочешь посмотреть?"
            elif final_score < 12:
                comment = "Ниже среднего, пока тебе не стоит становиться футбольным комментатором."
            elif final_score < 15:
                comment = "Неплохо, тебе уже разрешается оставлять умные комментарии под постами с футбольными новостями."
            elif final_score <= 19:
                comment = "Вау, ты наверняка ведёшь футбольный блог или телеграмм-канал, ты молодец!!!"
            else:
                comment = "ИДЕАЛЬНЫЙ РЕЗУЛЬТАТ!!! ТЫ БОГ ФУТБОЛА И МЕССИ С РОНАЛДУ НА ТЕБЯ РАВНЯЮТСЯ!!!!!!"
            score_rep = html.Div([html.Div(f"Итоговый результат: {final_score} из {state['max_rounds']} баллов"),
                                  html.Div(comment,
                                           style={'fontSize': '16px', 'fontWeight': 'normal', 'marginTop': '5px'})])
        else:
            if final_score < 5000:
                comment = "Нуууууу... не переживай, у меня есть dvd-диски с хоккейными матчами, хочешь посмотреть?"
            elif final_score < 6500:
                comment = "Ниже среднего, пока тебе не стоит становиться футбольным комментатором."
            elif final_score < 8000:
                comment = "Неплохо, тебе уже разрешается оставлять умные комментарии под постами с футбольными новостями."
            elif final_score < 9500:
                comment = "Вау, ты наверняка ведёшь футбольный блог или телеграмм-канал, ты молодец!!!"
            elif final_score >= 9500:
                comment = "ФЕНОМЕНАЛЬНЫЙ РЕЗУЛЬТАТ!!! ТЫ БОГ ФУТБОЛА И МЕССИ С РОНАЛДУ НА ТЕБЯ РАВНЯЮТСЯ!!!!!!"
            score_rep = html.Div([html.Div(f"Итоговый результат: {final_score} очков"), html.Div(comment, style={
                'fontSize': '16px', 'fontWeight': 'normal', 'marginTop': '5px'})])

        time_rep = f"Время прохождения: {total_time} сек"

        return (no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, None, None, {'display': 'block'}, score_rep, time_rep, table_element, chart_element, state)

    state['round'] += 1
    state['answered'] = False
    current_item = game_data[state['round'] - 1]

    round_txt = f"Раунд {state['round']} из {state['max_rounds']}"
    score_txt = f"Общий счет: {state['score']}"

    micro_shift = (state['round'] % 2) * 0.00001

    if is_player:
        top_row_text = f"👤 Футболист: {current_item['player']}"
        bottom_row_text = ""
        logo_img = html.Div("Фото отсутствует", className="text-muted my-3")
        for ext in ['.png', '.jpg', '.jpeg', '.webp', '.PNG', '.JPG', '.WEBP']:
            path = f"assets/players/{current_item['player']}{ext}"
            if os.path.exists(path):
                logo_img = html.Img(src=f"/assets/players/{current_item['player']}{ext}",
                                    style={'width': '100%', 'maxWidth': '280px', 'borderRadius': '12px',
                                           'boxShadow': '0 4px 12px rgba(0,0,0,0.15)'})
                break
        viewport_reset = dict(center=[50.0 + micro_shift, 10.0], zoom=5)
    else:
        top_row_text = html.H5(f"⚽ Клуб: {current_item['club']}", className="fw-bold mb-1 text-dark")
        bottom_row_text = html.P(f"🏟️ Стадион: {current_item['stadium']}", className="text-muted mb-0")
        logo_img = html.Div("Эмблема отсутствует", className="text-muted my-3")
        for ext in ['.png', '.jpg', '.jpeg', '.webp', '.PNG', '.JPG', '.WEBP']:
            path = f"assets/logos/{current_item['club']}{ext}"
            if os.path.exists(path):
                logo_img = html.Img(src=f"/assets/logos/{current_item['club']}{ext}",
                                    style={'width': '100%', 'maxWidth': '280px', 'borderRadius': '12px',
                                           'boxShadow': '0 4px 12px rgba(0,0,0,0.15)'})
                break

        if "eng" in state['active_mode'].lower() or "англ" in state['active_mode'].lower():
            viewport_reset = dict(center=[53.0 + micro_shift, -1.5], zoom=7)
        else:
            viewport_reset = dict(center=[50.0 + micro_shift, 10.0], zoom=5)

    return (round_txt, score_txt, top_row_text, bottom_row_text, logo_img, "", {'display': 'block'},
            {'display': 'none'}, True, [], viewport_reset, no_update, {'display': 'none'}, "", "", "", "", state)

@app.callback(
    Output('start-screen', 'style', allow_duplicate=True),
    Output('end-screen', 'style', allow_duplicate=True),
    Output('player-name-input', 'value', allow_duplicate=True),
    Input('restart-btn', 'n_clicks'),
    State('game-state', 'data'),
    prevent_initial_call=True
)
def back_to_menu(n_clicks, state):
    if n_clicks:
        saved_name = state.get('player_name', "Игрок")
        return {'padding': '50px 10px', 'maxWidth': '1300px', 'margin': '0 auto'}, {'display': 'none'}, saved_name
    return no_update, no_update, no_update

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=8050)