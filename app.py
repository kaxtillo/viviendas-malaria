import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import geopandas as gpd
from shapely.geometry import Polygon, shape
import requests

# Configuración de la página
st.set_page_config(page_title="Estimador de Población OSM", layout="wide")

st.title("🏙️ Estimador de Población con OpenStreetMap")
st.markdown("""
1. Usa las herramientas de dibujo en el mapa para seleccionar una zona.
2. La aplicación consultará los edificios directamente a OpenStreetMap y estimará la población.
""")

# Función para obtener datos de Overpass API (Sin necesidad de OSMnx)
def get_overpass_data(polygon):
    # Obtener coordenadas para el formato Overpass (poly:"lat1 lon1 lat2 lon2...")
    # Overpass usa (lat lon), Shapely usa (lon lat)
    coords = polygon.exterior.coords
    poly_str = " ".join([f"{lat} {lon}" for lon, lat in coords])
    
    overpass_query = f"""
    [out:json][timeout:25];
    (
      way["building"](poly:"{poly_str}");
      relation["building"](poly:"{poly_str}");
    );
    out geom;
    """
    url = "https://overpass-api.de/api/interpreter"
    response = requests.post(url, data={'data': overpass_query})
    return response.json()

# Columnas
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("1. Selecciona tu Zona")
    # Centrado en una ubicación inicial (ej. Bogotá)
    m = folium.Map(location=[4.6097, -74.0817], zoom_start=15)
    
    draw = Draw(
        export=False,
        position='topleft',
        draw_options={'polyline': False, 'circle': False, 'marker': False, 'circlemarker': False},
        edit_options={'edit': False}
    )
    draw.add_to(m)
    output = st_folium(m, width=800, height=500)

with col2:
    st.subheader("2. Resultados")
    
    if output and output.get("last_active_drawing"):
        geometry = output["last_active_drawing"]["geometry"]
        poly = shape(geometry)
        
        with st.spinner("Consultando OpenStreetMap..."):
            try:
                data = get_overpass_data(poly)
                
                # Convertir JSON de Overpass a GeoDataFrame
                features = []
                for element in data.get('elements', []):
                    if 'geometry' in element:
                        # Crear polígono a partir de los puntos de la geometría
                        geom_pts = [(p['lon'], p['lat']) for p in element['geometry']]
                        if len(geom_pts) >= 3:
                            features.append({
                                'geometry': Polygon(geom_pts),
                                'building': element.get('tags', {}).get('building', 'yes'),
                                'levels': element.get('tags', {}).get('building:levels', None)
                            })
                
                if features:
                    gdf = gpd.GeoDataFrame(features, crs="EPSG:4326")
                    
                    # Proyectar para calcular área en metros
                    gdf_proj = gdf.to_crs(gdf.estimate_utm_crs())
                    gdf_proj["area_m2"] = gdf_proj.geometry.area
                    
                    # Parámetros de estimación
                    pisos_default = st.slider("Pisos promedio (si no hay datos)", 1, 20, 2)
                    m2_persona = st.number_input("M² por persona (Densidad)", value=35, min_value=10)
                    
                    # Limpieza y cálculo de niveles
                    def clean_levels(val):
                        try:
                            return float(val)
                        except:
                            return pisos_default
                            
                    gdf_proj["niveles"] = gdf_proj["levels"].apply(clean_levels)
                    gdf_proj["area_habitable"] = gdf_proj["area_m2"] * gdf_proj["niveles"]
                    
                    # Totales
                    poblacion = gdf_proj["area_habitable"].sum() / m2_persona
                    
                    st.success("¡Análisis completado!")
                    m1, m2 = st.columns(2)
                    m1.metric("Edificios", len(gdf_proj))
                    m2.metric("Población Est.", int(poblacion))
                    
                    st.dataframe(gdf_proj[['building', 'area_m2', 'niveles']].head(10))
                else:
                    st.warning("No se detectaron edificios en esta zona.")
                    
            except Exception as e:
                st.error(f"Error procesando datos: {e}")
    else:
        st.info("Dibuja un polígono en el mapa para iniciar el cálculo.")
