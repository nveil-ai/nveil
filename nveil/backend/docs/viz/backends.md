# Backends

The viz service selects the rendering backend based on mark types and coordinate system.

## Backend selection

| Backend | When used | Mark types |
|---------|-----------|-----------|
| **ECharts** | 2D / 3D charts, Cartesian / polar / parallel coordinates | Point (2D+3D), Line (2D+3D), Bar, Histogram, Box/Violin, Candle, Parallel, Partition, Sector, Surface, Contour, Flow, VectorField |
| **VTK** | 3D scientific visualization | Voxel, MeshCell |
| **DeckGL** | Geospatial maps, GEO coordinates | Choropleth, Point (with lat/lon) |
| **Graph** | Network visualization | Node (with edge data) |
| **HTML** | Raw HTML embedding | Text / KPI cards |

## ECharts Backend

`backends/echarts_backend.py`

Renders 2D and 3D charts using Apache ECharts (+ echarts-gl for 3D). Supports:

- Scatter, line, bar, histogram, box, candle, parallel, sunburst/treemap
- Polar bar, pie/donut (sector)
- 3D scatter, line, surface, flowGL
- Violin + contour via Apache's `echarts-custom-series` bundles
- Theme tokens read inline per mark (no post-processor)

## VTK Backend

`backends/vtk_backend.py`

Renders 3D scientific visualizations using VTK. Supports:

- Surface meshes with color mapping
- Contour plots (2D/3D iso-surfaces)
- Volumetric rendering (voxel, uniform grid)
- Unstructured mesh cells
- Cube axes, color bars, camera controls

## DeckGL Backend

`backends/deckgl_backend.py`

Renders geospatial visualizations using Deck.GL. Supports:

- Choropleth maps (GeoJSON polygons)
- Point layers on maps
- Color-coded regions
- Tooltips and hover interactions

## Graph Backend

`backends/graph_backend.py`

Network/graph visualization using force-directed layout.

## HTML Backend

`backends/html_backend.py`

Embeds raw HTML content (e.g., custom widgets, embedded content).
