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
    """Calcula el área en m2 usando la aproximación de authalic sphere"""
    from math import radians, cos, sin, asin, sqrt
    # Radio de la tierra en metros
    R = 6371000
    lat_ref = poly.centroid.y
    # Factor de corrección por latitud
    arg = radians(lat_ref)
    # Aproximación de área para polígonos pequeños
    return poly.area * (radians(1)*R)**2 * cos(arg)

def buscar_lugar(nombre):
    geolocator = Nominatim(user_agent="my_osm_app_v1")
    location = geolocator.geocode(nombre)
    return location

# --- INTERFAZ ---
st.title("🏙️ Analizador de Vivienda y Población")

# Buscador en la parte superior
with st.expander("🔍 Buscador de Ubicación (Barrios, Veredas, Ciudades)", expanded=True):
    col_busq, col_btn = st.columns([4, 1])
    lugar_input = col_busq.text_input("Escribe el lugar:", placeholder="Ej: Barrio Chapinero, Bogotá")
    if col_btn.button("Ir al lugar"):
        loc = buscar_lugar(lugar_input)
        if loc:
            st.session_state.map_center = [loc.latitude, loc.longitude]
            st.success(f"Ubicado: {loc.address}")
        else:
            st.error("No se encontró el lugar.")

# Centro del mapa por defecto
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
    output = st_folium(m, width="100%", height=600, key="mapa_principal")

with col2:
    st.subheader("2. Análisis de Población")
    
    if output and output.get("last_active_drawing"):
        with st.spinner("Extrayendo polígonos de viviendas..."):
            geom = output["last_active_drawing"]["geometry"]
            poly = shape(geom)
            coords = poly.exterior.coords
            poly_str = " ".join([f"{lat} {lon}" for lon, lat in coords])
            
            # Consulta específica para viviendas
            query = f"""
            [out:json];
            (
              way["building"](poly:"{poly_str}");
              relation["building"](poly:"{poly_str}");
            );
            out geom;
            """
            try:
                r = requests.post("https://overpass-api.de/api/interpreter", data={'data': query})
                data = r.json()
                
                edificios = []
                for el in data.get('elements', []):
                    if 'geometry' in el:
                        lats = [p['lat'] for p in el['geometry']]
                        lons = [p['lon'] for p in el['geometry']]
                        b_poly = Polygon(zip(lons, lats))
                        
                        area_real = calcular_area_precision(b_poly)
                        
                        # Filtrar solo si tiene etiquetas de construcción
                        tipo = el.get('tags', {}).get('building', 'yes')
                        niveles = el.get('tags', {}).get('building:levels', 1)
                        
                        edificios.append({
                            'ID_OSM': el.get('id'),
                            'Tipo': tipo,
                            'Pisos': niveles,
                            'Area_Base_m2': round(area_real, 2)
                        })

                if edificios:
                    df = pd.DataFrame(edificios)
                    
                    # Controles de usuario
                    pisos_est = st.slider("Asumir niveles si OSM no tiene el dato:", 1, 15, 2)
                    m2_per = st.number_input("Metros cuadrados por persona:", value=35)
                    
                    # Limpiar columna de pisos (algunos vienen como texto o nulos)
                    df['Pisos'] = pd.to_numeric(df['Pisos'], errors='coerce').fillna(pisos_est)
                    df['Area_Total_Habitable'] = df['Area_Base_m2'] * df['Pisos']
                    
                    total_pob = df['Area_Total_Habitable'].sum() / m2_per
                    
                    st.metric("Viviendas detectadas", len(df))
                    st.metric("Población Estimada", f"{int(total_pob)} hab.")
                    
                    st.write("### Vista previa de datos")
                    st.dataframe(df.head(10))

                    # --- BOTONES DE DESCARGA ---
                    st.write("### Exportar Resultados")
                    c1, c2 = st.columns(2)
                    
                    # CSV
                    csv = df.to_csv(index=False).encode('utf-8')
                    c1.download_button("Descargar CSV", data=csv, file_name="poblacion_osm.csv", mime="text/csv")
                    
                    # Excel
                    output_xlsx = io.BytesIO()
                    with pd.ExcelWriter(output_xlsx, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False, sheet_name='Datos_Poblacion')
                    c2.download_button("Descargar Excel (XLSX)", data=output_xlsx.getvalue(), file_name="poblacion_osm.xlsx")

                else:
                    st.warning("No se encontraron polígonos de edificios en esta zona específica.")
            except Exception as e:
                st.error(f"Error de conexión: {e}")
    else:
        st.info("Utiliza el buscador para ir a tu zona y luego dibuja un área para calcular.")
