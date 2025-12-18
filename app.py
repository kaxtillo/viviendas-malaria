import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import requests
import pandas as pd
from shapely.geometry import Polygon, shape
from geopy.geocoders import Nominatim
import io
import plotly.express as px

st.set_page_config(page_title="Analizador Urbano OSM", layout="wide")

# --- FUNCIONES DE APOYO ---
def calcular_area_precision(poly):
    from math import radians, cos
    R = 6371000 # Radio Tierra
    lat_ref = poly.centroid.y
    arg = radians(lat_ref)
    return poly.area * (radians(1)*R)**2 * cos(arg)

def buscar_lugar(nombre):
    geolocator = Nominatim(user_agent="my_osm_app_v2")
    try:
        return geolocator.geocode(nombre)
    except:
        return None

# --- INTERFAZ ---
st.title("🏙️ Analizador de Vivienda y Población")

with st.expander("🔍 Buscador de Ubicación", expanded=True):
    col_busq, col_btn = st.columns([4, 1])
    lugar_input = col_busq.text_input("Escribe el lugar:", placeholder="Ej: Popayán, Cauca")
    if col_btn.button("Ir al lugar"):
        loc = buscar_lugar(lugar_input)
        if loc:
            st.session_state.map_center = [loc.latitude, loc.longitude]
            st.success(f"Ubicado: {loc.address}")
        else:
            st.error("No se encontró el lugar.")

if 'map_center' not in st.session_state:
    st.session_state.map_center = [4.6097, -74.0817]

col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("1. Mapa de Selección")
    m = folium.Map(location=st.session_state.map_center, zoom_start=16)
    draw = Draw(export=False, position='topleft', 
                draw_options={'polyline': False, 'circle': False, 'marker': False, 'circlemarker': False})
    draw.add_to(m)
    output = st_folium(m, width="100%", height=600, key="mapa_v3")

with col2:
    st.subheader("2. Análisis de Datos")
    
    if output and output.get("last_active_drawing"):
        with st.spinner("Procesando polígonos..."):
            geom = output["last_active_drawing"]["geometry"]
            poly = shape(geom)
            coords = poly.exterior.coords
            poly_str = " ".join([f"{lat} {lon}" for lon, lat in coords])
            
            query = f'[out:json];(way["building"](poly:"{poly_str}");relation["building"](poly:"{poly_str}"););out geom;'
            
            try:
                r = requests.post("https://overpass-api.de/api/interpreter", data={'data': query})
                data = r.json()
                
                edificios = []
                for el in data.get('elements', []):
                    if 'geometry' in el:
                        lats = [p['lat'] for p in el['geometry']]
                        lons = [p['lon'] for p in el['geometry']]
                        b_poly = Polygon(zip(lons, lats))
                        
                        edificios.append({
                            'Tipo': el.get('tags', {}).get('building', 'Otros'),
                            'Pisos': el.get('tags', {}).get('building:levels', None),
                            'Area_Base': calcular_area_precision(b_poly)
                        })

                if edificios:
                    df = pd.DataFrame(edificios)
                    
                    # Ajustes de usuario
                    p_est = st.slider("Pisos por defecto", 1, 15, 2)
                    m2_per = st.number_input("M2 por persona", value=35)
                    
                    # Limpieza
                    df['Pisos'] = pd.to_numeric(df['Pisos'], errors='coerce').fillna(p_est).astype(int)
                    df['Area_Habitable'] = df['Area_Base'] * df['Pisos']
                    
                    # Métricas
                    total_pob = df['Area_Habitable'].sum() / m2_per
                    st.metric("Población Estimada", f"{int(total_pob)} personas")
                    
                    # --- GRÁFICO DE PASTEL ---
                    st.write("### Distribución por Altura (Pisos)")
                    # Agrupar datos para el gráfico
                    df_grafico = df['Pisos'].value_counts().reset_index()
                    df_grafico.columns = ['Niveles', 'Cantidad']
                    df_grafico['Niveles'] = df_grafico['Niveles'].apply(lambda x: f"{int(x)} Piso(s)")

                    fig = px.pie(df_grafico, values='Cantidad', names='Niveles', 
                                 hole=0.4, # Gráfico de dona para que se vea más moderno
                                 color_discrete_sequence=px.colors.sequential.RdBu)
                    
                    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
                    st.plotly_chart(fig, use_container_width=True)

                    # --- EXPORTAR ---
                    st.write("### Exportar")
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button("Descargar CSV", csv, "datos.csv", "text/csv")
                    
                    output_xlsx = io.BytesIO()
                    with pd.ExcelWriter(output_xlsx, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False)
                    st.download_button("Descargar Excel", output_xlsx.getvalue(), "datos.xlsx")
                    
                else:
                    st.warning("No se encontraron edificios.")
            except Exception as e:
                st.error(f"Error: {e}")
    else:
        st.info("Dibuja una zona en el mapa para ver el análisis.")
