import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import requests
import pandas as pd
from shapely.geometry import Polygon, shape

st.set_page_config(page_title="Estimador Población", layout="wide")

st.title("🏙️ Estimador de Población Local")

col1, col2 = st.columns([3, 2])

with col1:
    m = folium.Map(location=[4.6097, -74.0817], zoom_start=15)
    draw = Draw(export=False, position='topleft', 
                draw_options={'polyline': False, 'circle': False, 'marker': False, 'circlemarker': False})
    draw.add_to(m)
    output = st_folium(m, width=700, height=500)

with col2:
    st.subheader("Resultados")
    
    if output and output.get("last_active_drawing"):
        with st.spinner("Analizando zona..."):
            # 1. Obtener geometría
            geom = output["last_active_drawing"]["geometry"]
            poly = shape(geom)
            coords = poly.exterior.coords
            poly_str = " ".join([f"{lat} {lon}" for lon, lat in coords])
            
            # 2. Consulta Overpass (Edificios)
            query = f'[out:json];(way["building"](poly:"{poly_str}");relation["building"](poly:"{poly_str}"););out geom;'
            try:
                r = requests.post("https://overpass-api.de/api/interpreter", data={'data': query})
                data = r.json()
                
                edificios = []
                for el in data.get('elements', []):
                    # Calcular área aproximada (simplificada: 1 grado lat ≈ 111km)
                    if 'geometry' in el:
                        lats = [p['lat'] for p in el['geometry']]
                        lons = [p['lon'] for p in el['geometry']]
                        # Cálculo de área simplificado en m2 (Aprox. para zonas pequeñas)
                        area = Polygon(zip(lons, lats)).area * 10**10 * 1.23 
                        
                        edificios.append({
                            'tipo': el.get('tags', {}).get('building', 'residencia'),
                            'niveles': int(el.get('tags', {}).get('building:levels', 1)),
                            'area_m2': round(area, 2)
                        })

                if edificios:
                    df = pd.DataFrame(edificios)
                    
                    p_promedio = st.slider("Pisos si no hay dato", 1, 10, 2)
                    m2_persona = st.number_input("M2 por persona", value=30)
                    
                    df['niveles'] = df['niveles'].replace(1, p_promedio) # Ajuste simple
                    total_m2 = (df['area_m2'] * df['niveles']).sum()
                    poblacion = total_m2 / m2_persona
                    
                    st.metric("Edificios encontrados", len(df))
                    st.metric("Población Estimada", int(poblacion))
                    st.dataframe(df.head())
                else:
                    st.warning("No hay edificios en esta zona.")
            except Exception as e:
                st.error(f"Error: {e}")
    else:
        st.info("Dibuja un área en el mapa.")
