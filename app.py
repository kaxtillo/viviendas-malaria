import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import requests
import pandas as pd
from shapely.geometry import Polygon, shape
from geopy.geocoders import Nominatim
import io

st.set_page_config(page_title="Analizador Urbano OSM", layout="wide")

# --- FUNCIONES DE APOYO ---
def calcular_area_precision(poly):
    from math import radians, cos
    R = 6371000  # Radio Tierra en metros
    lat_ref = poly.centroid.y
    arg = radians(lat_ref)
    # Cálculo preciso basado en latitud
    return poly.area * (radians(1)*R)**2 * cos(arg)

def buscar_lugar(nombre):
    geolocator = Nominatim(user_agent="my_osm_app_v3")
    try:
        return geolocator.geocode(nombre)
    except:
        return None

# --- INTERFAZ ---
st.title("🏙️ Analizador de Vivienda y Población")

with st.expander("🔍 Buscador de Ubicación (Barrios, Veredas, Ciudades)", expanded=True):
    col_busq, col_btn = st.columns([4, 1])
    lugar_input = col_busq.text_input("Escribe el lugar:", placeholder="Ej: Centro Histórico, Popayán")
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
    draw = Draw(
        export=False, 
        position='topleft', 
        draw_options={'polyline': False, 'circle': False, 'marker': False, 'circlemarker': False}
    )
    draw.add_to(m)
    output = st_folium(m, width="100%", height=600, key="mapa_final")

with col2:
    st.subheader("2. Resultados del Análisis")
    
    if output and output.get("last_active_drawing"):
        with st.spinner("Calculando datos..."):
            geom = output["last_active_drawing"]["geometry"]
            poly = shape(geom)
            coords = poly.exterior.coords
            poly_str = " ".join([f"{lat} {lon}" for lon, lat in coords])
            
            # Consulta a Overpass
            query = f'[out:json];(way["building"](poly:"{poly_str}");relation["building"](poly:"{poly_str}"););out geom;'
            
            try:
                # Modificamos los headers para identificarnos correctamente ante el servidor de OSM
                headers = {'User-Agent': 'ViviendasMalariaApp/1.0 (https://github.com/kaxtillo/viviendas-malaria)'}
                r = requests.post("https://overpass-api.de/api/interpreter", data={'data': query}, headers=headers, timeout=30)
                
                # Verificar si el servidor respondió con un código de error HTTP
                if r.status_code != 200:
                    st.error(f"El servidor de OpenStreetMap está saturado (Código HTTP {r.status_code}). Por favor, intenta de nuevo en unos segundos o dibuja un área más pequeña.")
                else:
                    data = r.json()
                    
                    edificios = []
                    for el in data.get('elements', []):
                        if 'geometry' in el:
                            lats = [p['lat'] for p in el['geometry']]
                            lons = [p['lon'] for p in el['geometry']]
                            b_poly = Polygon(zip(lons, lats))
                            
                            area_b = calcular_area_precision(b_poly)
                            pisos = el.get('tags', {}).get('building:levels', 1)
                            
                            edificios.append({
                                'ID_OSM': el.get('id'),
                                'Uso': el.get('tags', {}).get('building', 'residencial'),
                                'Pisos': pisos,
                                'Area_m2': round(area_b, 2)
                            })

                    if edificios:
                        df = pd.DataFrame(edificios)
                        
                        df['Pisos'] = pd.to_numeric(df['Pisos'], errors='coerce').fillna(1).astype(int)
                        df['Area_Total'] = df['Area_m2'] * df['Pisos']
                        
                        m2_per = st.number_input("M2 por persona (Densidad)", value=35)
                        
                        total_viviendas = len(df)
                        total_pob = int(df['Area_Total'].sum() / m2_per)
                        
                        st.divider()
                        st.metric("Total de Viviendas Detectadas", f"{total_viviendas}")
                        st.metric("Población Estimada", f"{total_pob} hab.")
                        st.divider()

                        st.write("### Tabla de detalles")
                        st.dataframe(df[['Uso', 'Pisos', 'Area_m2', 'Area_Total']].head(20))

                        st.write("### Exportar Informe")
                        c1, c2 = st.columns(2)
                        
                        csv = df.to_csv(index=False).encode('utf-8')
                        c1.download_button("Descargar CSV", csv, "analisis_vivienda.csv", "text/csv")
                        
                        output_xlsx = io.BytesIO()
                        with pd.ExcelWriter(output_xlsx, engine='xlsxwriter') as writer:
                            df.to_excel(writer, index=False, sheet_name='Análisis')
                        c2.download_button("Descargar Excel (XLSX)", output_xlsx.getvalue(), "analisis_vivienda.xlsx")
                    else:
                        st.warning("No se encontraron viviendas en el área seleccionada.")
                        
            except requests.exceptions.Timeout:
                st.error("⏱️ La consulta tardó demasiado tiempo en responder. Intenta dibujar un área más pequeña.")
            except Exception as e:
                st.error(f"Error al procesar los datos de OpenStreetMap: {e}")
                st.info("Sugerencia: Esto ocurre cuando el servidor público de OSM rechaza la petición por tamaño o saturación. Prueba reduciendo el área del polígono.")

