import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import osmnx as ox
import geopandas as gpd
from shapely.geometry import Polygon

# Configuración de la página
st.set_page_config(page_title="Estimador de Población OSM", layout="wide")

st.title("🏙️ Estimador de Población con OpenStreetMap")
st.markdown("""
1. Usa las herramientas de dibujo (cuadrado o polígono) en el mapa de la izquierda para seleccionar una zona.
2. La aplicación descargará las viviendas y estimará la población.
""")

# Dividir la pantalla en dos columnas
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("1. Selecciona tu Zona")
    # Mapa base centrado (puedes cambiar las coordenadas iniciales)
    m = folium.Map(location=[4.6097, -74.0817], zoom_start=15) # Ejemplo: Bogotá
    
    # Añadir herramientas de dibujo
    draw = Draw(
        export=False,
        position='topleft',
        draw_options={'polyline': False, 'circle': False, 'marker': False, 'circlemarker': False},
        edit_options={'edit': False}
    )
    draw.add_to(m)

    # Mostrar mapa y capturar el dibujo del usuario
    output = st_folium(m, width=800, height=500)

with col2:
    st.subheader("2. Resultados")
    
    # Verificar si el usuario ha dibujado algo
    if output["last_active_drawing"]:
        # Obtener la geometría dibujada
        geometry = output["last_active_drawing"]["geometry"]
        coords = geometry["coordinates"][0]
        
        # Crear un objeto Polígono de Shapely (OSMnx requiere (longitud, latitud))
        poly = Polygon(coords)
        
        st.info("Descargando datos de OSM... esto puede tardar unos segundos.")
        
        try:
            # Descargar edificios dentro del polígono
            # tags={'building': True} trae todo lo que sea edificio
            gdf = ox.features_from_polygon(poly, tags={'building': True})
            
            if not gdf.empty:
                # Filtrar columnas relevantes y limpieza básica
                # Proyectar a UTM para medir áreas en metros cuadrados correctamente
                gdf_proj = gdf.to_crs(gdf.estimate_utm_crs())
                
                # Calcular área de cada huella de edificio
                gdf_proj["area_m2"] = gdf_proj.geometry.area
                
                # --- ALGORITMO DE ESTIMACIÓN ---
                
                # 1. Determinar niveles (pisos)
                # Si OSM no tiene el dato 'building:levels', asumimos un valor por defecto
                pisos_default = st.slider("Pisos promedio (si no hay datos en OSM)", 1, 10, 2)
                
                def get_levels(row):
                    if 'building:levels' in row and str(row['building:levels']).isnumeric():
                        return int(row['building:levels'])
                    return pisos_default

                gdf_proj["niveles"] = gdf_proj.apply(get_levels, axis=1)
                
                # 2. Calcular Área Habitable Total
                gdf_proj["area_total"] = gdf_proj["area_m2"] * gdf_proj["niveles"]
                
                # 3. Densidad (Metros cuadrados por persona)
                m2_por_persona = st.number_input("M² por persona (Densidad)", value=35, min_value=10)
                
                # Cálculo final
                poblacion_total = gdf_proj["area_total"].sum() / m2_por_persona
                num_edificios = len(gdf)
                
                # --- MOSTRAR RESULTADOS ---
                st.success("¡Cálculo completado!")
                
                metric1, metric2 = st.columns(2)
                metric1.metric("Edificios Detectados", f"{num_edificios}")
                metric2.metric("Población Estimada", f"{int(poblacion_total):,}")
                
                st.write("---")
                st.write("**Detalle de datos (Primeras 5 filas):**")
                # Mostrar tabla simplificada
                cols_to_show = ['building', 'area_m2', 'niveles']
                # Asegurarse que las columnas existen antes de mostrarlas
                cols_existentes = [c for c in cols_to_show if c in gdf_proj.columns]
                st.dataframe(gdf_proj[cols_existentes].head())
                
            else:
                st.warning("No se encontraron edificios en esa zona.")
                
        except Exception as e:
            st.error(f"Ocurrió un error: {e}")
            st.caption("Intenta dibujar un área más pequeña.")
            
    else:
        st.info("👆 Dibuja un rectángulo o polígono en el mapa para comenzar.")
