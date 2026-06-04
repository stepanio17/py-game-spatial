import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic
import os
import requests
from shapely.geometry import Point, shape

# 1. НАСТРОЙКА СТРАНИЦЫ И КОНСТАНТ
st.set_page_config(page_title="Футбольный GeoGuesser", layout="wide")

# Инъекция CSS для изменения курсора мыши над картой на прицел-перекрестие
st.markdown("""
    <style>
    .leaflet-container {
        cursor: crosshair !important;
    }
    </style>
""", unsafe_allow_html=True)

FILE_NAME = "DataForSpatialGame.xlsx"
EUROPE_GEOJSON_URL = "https://raw.githubusercontent.com/leakyMirror/map-of-europe/master/GeoJSON/europe.geojson"


# Загрузка названий режимов (вкладок)
@st.cache_data
def get_game_modes():
    if os.path.exists(FILE_NAME):
        try:
            xls = pd.ExcelFile(FILE_NAME)
            return xls.sheet_names
        except Exception as e:
            st.error(f"Ошибка при чтении структуры Excel: {e}")
            return []
    else:
        st.warning(f"Файл '{FILE_NAME}' не найден.")
        return []


# Функция для загрузки данных листа
@st.cache_data
def load_sheet_data(sheet_name):
    try:
        df_sheet = pd.read_excel(FILE_NAME, sheet_name=sheet_name)

        if "player" not in sheet_name.lower() and "игрок" not in sheet_name.lower():
            if df_sheet is not None and 'lat' in df_sheet.columns and 'lon' in df_sheet.columns:
                df_sheet['lat'] = df_sheet['lat'].astype(str).str.replace(',', '.', regex=False).str.strip()
                df_sheet['lon'] = df_sheet['lon'].astype(str).str.replace(',', '.', regex=False).str.strip()
                df_sheet['lat'] = pd.to_numeric(df_sheet['lat'], errors='coerce')
                df_sheet['lon'] = pd.to_numeric(df_sheet['lon'], errors='coerce')
                df_sheet = df_sheet.dropna(subset=['lat', 'lon'])
        return df_sheet
    except Exception as e:
        st.error(f"Ошибка при загрузке листа {sheet_name}: {e}")
        return None


# Кэширование геоданных границ стран Европы
@st.cache_data
def load_europe_geojson():
    try:
        response = requests.get(EUROPE_GEOJSON_URL)
        return response.json()
    except Exception as e:
        st.error(f"Не удалось загрузить карту границ Европы: {e}")
        return None


modes = get_game_modes()
europe_geojson = load_europe_geojson()


# ДОБАВЛЕНО: ГИС-фильтр для разделения Великобритании по координатам клика
def refine_uk_region(lat, lon):
    # 1. Северная Ирландия (отдельный остров на западе)
    if lon < -5.4 and lat > 54.0:
        return "Northern Ireland"
    # 2. Шотландия (все что севернее исторической границы с Англией)
    if lat > 55.75:
        return "Scotland"
    # 3. Уэльс (западный географический выступ)
    if -5.3 <= lon <= -2.65 and 51.35 <= lat <= 53.45:
        return "Wales"
    # 4. Все остальное — Англия
    return "England"


# 2. ИНИЦИАЛИЗАЦИЯ ИГРОВОГО СОСТОЯНИЯ
if modes and europe_geojson:
    if "game_started" not in st.session_state:
        st.session_state.game_started = False
        st.session_state.game_over = False


    def start_new_game(selected_mode):
        mode_df = load_sheet_data(selected_mode)
        if mode_df is not None:
            is_player_mode = "player" in selected_mode.lower() or "игрок" in selected_mode.lower()
            required_cols = {'player', 'country'} if is_player_mode else {'club', 'stadium', 'city', 'lat', 'lon'}

            if not required_cols.issubset(mode_df.columns):
                st.error(
                    f"Неверные колонки! Для игроков нужны: player, country. Для стадионов: club, stadium, city, lat, lon")
                return

            total_rounds = min(10, len(mode_df))
            sampled_df = mode_df.sample(total_rounds)

            st.session_state.game_clubs = sampled_df.to_dict(orient='records')
            st.session_state.max_rounds = total_rounds
            st.session_state.current_round = 1
            st.session_state.score = 0
            st.session_state.answered = False
            st.session_state.game_started = True
            st.session_state.game_over = False
            st.session_state.history = []
            st.session_state.active_mode = selected_mode
            st.session_state.is_player_game = is_player_mode
            st.session_state.clicked_country_feature = None
            st.session_state.correct_country_feature = None


    def next_round():
        if st.session_state.current_round >= st.session_state.max_rounds:
            st.session_state.game_over = True
        else:
            st.session_state.current_round += 1
            st.session_state.answered = False
            st.session_state.clicked_country_feature = None
            st.session_state.correct_country_feature = None


    # 3. ИНТЕРФЕЙС
    if not st.session_state.game_started:
        st.title("⚽ Football GeoGuesser")
        st.write("Добро пожаловать в ГИС-викторину! Выберите режим игры ниже.")
        chosen_mode = st.radio("Доступные режимы из вашего Excel:", modes)
        st.button("Начать игру 🚀", on_click=start_new_game, args=(chosen_mode,), type="primary")

    elif st.session_state.game_over:
        st.title("🏆 Игра окончена! Результаты анализа")
        hist_df = pd.DataFrame(st.session_state.history)

        if st.session_state.is_player_game:
            st.metric("Итоговый результат", f"{st.session_state.score} из {st.session_state.max_rounds} очков")
            st.subheader("📊 Ваша точность по игрокам:")
            hist_df['Результат'] = hist_df['points'].apply(lambda x: "Правильно" if x == 1 else "Ошибка")
            st.dataframe(hist_df[['item', 'correct_country', 'clicked_country', 'Результат']])
        else:
            avg_err = hist_df['distance'].mean()
            best_round = hist_df.loc[hist_df['distance'].idxmin()]
            m1, m2, m3 = st.columns(3)
            m1.metric("Итоговый результат", f"{st.session_state.score} очков")
            m2.metric("Средняя ошибка", f"{avg_err:.1f} км.")
            m3.metric("Лучший раунд", f"{best_round['distance']:.1f} км. ({best_round['club']})")
            st.write("---")
            st.subheader("📊 Распределение пространственных ошибок")
            st.bar_chart(hist_df.set_index('club')['distance'])

        if st.button("В главное меню 🔄"):
            st.session_state.game_started = False
            st.rerun()

    else:
        current_item = st.session_state.game_clubs[st.session_state.current_round - 1]
        st.title(f"⚽ Режим: {st.session_state.active_mode}")
        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader(f"Раунд {st.session_state.current_round} из {st.session_state.max_rounds}")
            st.metric("Общий счет", st.session_state.score)
            st.write("---")

            if st.session_state.is_player_game:
                st.write("**Где родился этот футболист?**")
                player_name = current_item['player']

                player_found = False
                for ext in ['.png', '.jpg', '.jpeg', '.webp', '.PNG', '.JPG', '.WEBP']:
                    photo_path = f"players/{player_name}{ext}"
                    if os.path.exists(photo_path):
                        st.image(photo_path, width=250)
                        player_found = True
                        break

                if not player_found:
                    st.info(f"👤 Фото для **{player_name}** не найдено.")

                st.subheader(f"Футболист: {player_name}")

                if st.session_state.answered:
                    if st.session_state.last_points == 1:
                        st.success(f"🎉 Правильно! Это {current_item['country']}")
                    else:
                        clicked_name = st.session_state.last_clicked_country_name
                        st.error(f"❌ Неверно! Вы выбрали: {clicked_name}. Правильный ответ: {current_item['country']}")
                    st.button("Следующий раунд ➡️", on_click=next_round)

            else:
                logo_found = False
                for ext in ['.png', '.jpg', '.jpeg', '.webp', '.PNG', '.JPG', '.WEBP']:
                    local_logo_path = f"logos/{current_item['club']}{ext}"
                    if os.path.exists(local_logo_path):
                        st.image(local_logo_path, width=200)
                        logo_found = True
                        break
                if not logo_found:
                    st.info(f"🎭 Эмблема для {current_item['club']} отсутствует.")
                st.write(f"🏟️ **Стадион:** {current_item['stadium']}")

                if st.session_state.answered:
                    st.success(f"Правильный ответ: {current_item['city']} ({current_item['club']})")
                    st.write(f"Ошибка расстояния: **{st.session_state.last_distance:.1f} км**")
                    st.button("Следующий раунд ➡️", on_click=next_round)

        with col2:
            st.subheader("Укажи положение на карте:")

            if "eng" in st.session_state.active_mode.lower() or "англ" in st.session_state.active_mode.lower():
                m = folium.Map(location=[53.0, -1.5], zoom_start=6, tiles="Cartodb Positron")
            else:
                m = folium.Map(location=[50.0, 10.0], zoom_start=4, tiles="Cartodb Positron")

            if st.session_state.is_player_game and st.session_state.answered:
                if st.session_state.correct_country_feature:
                    folium.GeoJson(
                        st.session_state.correct_country_feature,
                        style_function=lambda x: {'fillColor': 'green', 'color': 'green', 'fillOpacity': 0.5}
                    ).add_to(m)

                if st.session_state.last_points == 0 and st.session_state.clicked_country_feature:
                    folium.GeoJson(
                        st.session_state.clicked_country_feature,
                        style_function=lambda x: {'fillColor': 'red', 'color': 'red', 'fillOpacity': 0.5}
                    ).add_to(m)

            elif not st.session_state.is_player_game and st.session_state.answered and "click_coords" in st.session_state:
                folium.Marker(st.session_state.click_coords, icon=folium.Icon(color="red")).add_to(m)
                actual_coords = (current_item['lat'], current_item['lon'])
                folium.Marker(actual_coords, icon=folium.Icon(color="green")).add_to(m)
                folium.PolyLine([st.session_state.click_coords, actual_coords], color="blue", weight=3).add_to(m)

            map_data = st_folium(m, width=700, height=520, key="game_map")

            # ОБРАБОТКА КЛИКА
            if map_data and map_data.get("last_clicked") and not st.session_state.answered:
                click = map_data["last_clicked"]
                user_lat, user_lon = click["lat"], click["lng"]

                if st.session_state.is_player_game:
                    click_point = Point(user_lon, user_lat)
                    base_clicked_country = "Undefined"
                    selected_feature = None

                    # Ищем базовое попадание по глобальной карте GeoJSON
                    for feature in europe_geojson['features']:
                        polygon_shape = shape(feature['geometry'])
                        if polygon_shape.contains(click_point):
                            base_clicked_country = feature['properties'].get('NAME', feature['properties'].get('name',
                                                                                                               'Unknown'))
                            selected_feature = feature
                            break

                    if base_clicked_country in ["Undefined", "Unknown"]:
                        st.warning(
                            "📍 Вы кликнули мимо суши! Пожалуйста, прицельтесь точнее и выберите страну на карте.")
                    else:
                        st.session_state.click_coords = (user_lat, user_lon)
                        st.session_state.clicked_country_feature = selected_feature

                        # ИСПРАВЛЕНО: Если попали в UK, запускаем микро-анализ координат, чтобы узнать точный футбольный регион
                        if base_clicked_country == "United Kingdom":
                            final_clicked_country = refine_uk_region(user_lat, user_lon)
                        else:
                            final_clicked_country = base_clicked_country

                        correct_country_name = current_item['country']

                        # Ищем фичу для подсветки правильного ответа (для Англии/Уэльса подсветит общий UK полигон)
                        search_target = "United Kingdom" if correct_country_name.lower() in ["england", "scotland",
                                                                                             "wales",
                                                                                             "northern ireland"] else correct_country_name
                        for feature in europe_geojson['features']:
                            f_name = feature['properties'].get('NAME', feature['properties'].get('name', ''))
                            if f_name.lower() == search_target.lower():
                                st.session_state.correct_country_feature = feature
                                break

                        # ИСПРАВЛЕНО: Проверка строгого соответствия футбольного региона клика и таблицы
                        is_correct = final_clicked_country.lower() == correct_country_name.lower()

                        points = 1 if is_correct else 0
                        st.session_state.score += points
                        st.session_state.last_points = points
                        st.session_state.last_clicked_country_name = final_clicked_country
                        st.session_state.answered = True

                        st.session_state.history.append({
                            "item": current_item['player'],
                            "correct_country": correct_country_name,
                            "clicked_country": final_clicked_country,
                            "points": points
                        })
                        st.rerun()
                else:
                    st.session_state.click_coords = (user_lat, user_lon)
                    actual_coords = (current_item['lat'], current_item['lon'])
                    distance = geodesic(st.session_state.click_coords, actual_coords).km
                    st.session_state.last_distance = distance

                    st.session_state.history.append({
                        "club": current_item['club'],
                        "distance": distance,
                        "user_lat": user_lat, "user_lon": user_lon,
                        "actual_lat": current_item['lat'], "actual_lon": current_item['lon']
                    })

                    points = max(0, int(1000 - (distance * 2)))
                    st.session_state.score += points
                    st.session_state.answered = True
                    st.rerun()