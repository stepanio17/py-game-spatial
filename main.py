import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic
import os

# 1. НАСТРОЙКА СТРАНИЦЫ И ДАННЫХ
st.set_page_config(page_title="Футбольный GeoGuesser", layout="wide")


# Загрузка данных
@st.cache_data
def load_data():
    file_name = "DataForSpatialGame.xlsx"
    if os.path.exists(file_name):
        try:
            return pd.read_excel(file_name)
        # ИСПРАВЛЕНО: добавлено "Exception as e" для корректной работы лога ошибки
        except Exception as e:
            st.error(f"Ошибка при чтении файла: {e}")
            return None
    else:
        st.warning(f"Файл {file_name} не найден")
        return None


df = load_data()

# 2. ИНИЦИАЛИЗАЦИЯ ИГРОВОГО СОСТОЯНИЯ (Session State)
if df is not None:
    required_columns = {'club', 'stadium', 'city', 'lat', 'lon'}
    if not required_columns.issubset(df.columns):
        st.error(f"Неправильный формат таблицы")
    else:
        if "game_started" not in st.session_state:
            st.session_state.game_started = False
            st.session_state.game_over = False


        def start_new_game():
            total_rounds = min(15, len(df))
            sampled_df = df.sample(total_rounds)

            st.session_state.game_clubs = sampled_df.to_dict(orient='records')
            st.session_state.max_rounds = total_rounds
            st.session_state.current_round = 1
            st.session_state.score = 0
            st.session_state.answered = False
            st.session_state.last_distance = None
            st.session_state.game_started = True
            st.session_state.game_over = False
            # ДОБАВЛЕНО: хранилище для истории раундов (база для дашборда)
            st.session_state.history = []


        def next_round():
            # ИСПРАВЛЕНО: заменено опечатка '>-' на оператор '>='
            if st.session_state.current_round >= st.session_state.max_rounds:
                st.session_state.game_over = True
            else:
                st.session_state.current_round += 1
                st.session_state.answered = False
                st.session_state.last_distance = None


        # 3. ИНТЕРФЕЙС

        # ЭКРАН 1: СТАРТОВОЕ МЕНЮ
        if not st.session_state.game_started:
            st.title("Football GeoGuesser")
            st.write(
                "Проверь, насколько ты разбираешься в футболе. Правила: Тебе будут показана эмблема клуба и стадион. Кликни по карте туда, где этот стадион находится.")
            st.button("Начать игру", on_click=start_new_game, type="primary")

        # ЭКРАН 2: ФИНАЛЬНЫЙ ГИС-ДАШБОРД (ПОЛНОСТЬЮ ПЕРЕРАБОТАН)
        elif st.session_state.game_over:
            st.balloons()
            st.title("🏆 Игра окончена! Финальный анализ")

            # Переводим историю в датафрейм для аналитики
            hist_df = pd.DataFrame(st.session_state.history)

            # Считаем пространственные метрики
            avg_err = hist_df['distance'].mean()
            best_round = hist_df.loc[hist_df['distance'].idxmin()]

            # Выводим ключевые метрики в красивых блоках
            m1, m2, m3 = st.columns(3)
            m1.metric("Итоговый результат", f"{st.session_state.score} очков")
            m2.metric("Средняя ошибка расстояния", f"{avg_err:.1f} км")
            m3.metric("Лучшая точность", f"{best_round['distance']:.1f} км ({best_round['club']})")

            st.write("---")

            # Разделяем экран финала на график и карту ошибок
            dash_col1, dash_col2 = st.columns([1, 1])

            with dash_col1:
                st.subheader("📊 Анализ ошибок по клубам")
                st.write("График показывает, на сколько километров ты промахнулся в каждом раунде:")
                # Строим столбчатую диаграмму отклонений
                chart_data = hist_df.set_index('club')['distance']
                st.bar_chart(chart_data)

                st.button("Играть снова 🔄", on_click=start_new_game, type="primary")

            with dash_col2:
                st.subheader("🗺️ Карта прогнозов")
                st.write("Красные точки — твои клики, зеленые — стадионы. Синие линии — векторы твоих ошибок.")

                # Создаем общую финальную карту
                final_map = folium.Map(location=[53.0, -1.5], zoom_start=6, tiles="Cartodb Positron")

                # Отрисовываем данные из истории всех 15 раундов
                for _, row in hist_df.iterrows():
                    u_coords = (row['user_lat'], row['user_lon'])
                    a_coords = (row['actual_lat'], row['actual_lon'])

                    folium.Marker(u_coords, popup=f"Твой выбор для {row['club']}",
                                  icon=folium.Icon(color="red", icon="question")).add_to(final_map)
                    folium.Marker(a_coords, popup=f"Стадион {row['club']}",
                                  icon=folium.Icon(color="green", icon="trophy", prefix="fa")).add_to(final_map)
                    folium.PolyLine([u_coords, a_coords], color="blue", weight=2, opacity=0.6).add_to(final_map)

                st_folium(final_map, width=600, height=450, key="final_analysis_map")

        # ЭКРАН 3: ИГРОВОЙ ПРОЦЕСС
        else:
            current_club = st.session_state.game_clubs[st.session_state.current_round - 1]

            st.title("⚽ Футбольный GeoGuesser")
            col1, col2 = st.columns([1, 2])

            with col1:
                st.subheader(f"Раунд {st.session_state.current_round} из {st.session_state.max_rounds}")
                st.metric("Общий счет", st.session_state.score)
                st.write("---")

                # ЛОГИКА ОТОБРАЖЕНИЯ ЭМБЛЕМЫ
                local_logo_path = f"logos/{current_club['club']}.png"

                if os.path.exists(local_logo_path):
                    st.image(local_logo_path, width=200)
                elif 'logo_url' in current_club and pd.notna(current_club['logo_url']):
                    st.image(current_club['logo_url'], width=200)
                else:
                    st.info(f"🎭 Эмблема для **{current_club['club']}** не загружена.")

                st.write(f"🏟️ **Стадион:** {current_club['stadium']}")

                if st.session_state.answered:
                    st.success(f"Правильный ответ: {current_club['city']} ({current_club['club']})")
                    st.write(f"Ошибка расстояния: **{st.session_state.last_distance:.1f} км**")
                    st.button("Следующий раунд ➡️", on_click=next_round)

            with col2:
                st.subheader("Укажи положение стадиона на карте:")

                m = folium.Map(location=[53.0, -1.5], zoom_start=6, tiles="Cartodb Positron")

                if st.session_state.answered and "click_coords" in st.session_state:
                    user_coords = st.session_state.click_coords
                    actual_coords = (current_club['lat'], current_club['lon'])

                    folium.Marker(user_coords, tooltip="Твой выбор", icon=folium.Icon(color="red")).add_to(m)
                    folium.Marker(actual_coords, tooltip=current_club['club'], icon=folium.Icon(color="green")).add_to(
                        m)
                    folium.PolyLine([user_coords, actual_coords], color="blue", weight=3, opacity=0.7).add_to(m)

                map_data = st_folium(m, width=700, height=500, key="game_map")

                # ОБРАБОТКА ОТВЕТА И СБОР ДАННЫХ ДЛЯ ДАШБОРДА
                if map_data and map_data.get("last_clicked") and not st.session_state.answered:
                    click = map_data["last_clicked"]
                    user_lat, user_lon = click["lat"], click["lng"]

                    st.session_state.click_coords = (user_lat, user_lon)
                    actual_coords = (current_club['lat'], current_club['lon'])

                    distance = geodesic(st.session_state.click_coords, actual_coords).km
                    st.session_state.last_distance = distance

                    # ДОБАВЛЕНО: Запись результатов текущего раунда в историю для итогового дашборда
                    st.session_state.history.append({
                        "club": current_club['club'],
                        "distance": distance,
                        "user_lat": user_lat,
                        "user_lon": user_lon,
                        "actual_lat": current_club['lat'],
                        "actual_lon": current_club['lon']
                    })

                    points = max(0, int(1000 - (distance * 2)))
                    st.session_state.score += points
                    st.session_state.answered = True
                    st.rerun()