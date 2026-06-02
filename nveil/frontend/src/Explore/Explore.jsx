// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Guillaume Franque
// SPDX-License-Identifier: AGPL-3.0-or-later

import styles from "./Explore.module.css";
import { useTranslation } from "react-i18next";
import { useState, useRef, useCallback, Suspense, lazy, useEffect, useMemo } from "react";
import PaletteGallery from "../Components/Palette/PaletteGallery";
import SEO from "../Components/SEO";
import ShowcaseCard from "./ShowcaseCard";

import voxel from "./thumbnails/volumetricvoxel.webp";
import choregraph from "./thumbnails/choregraph.jpg";
import mapThumb from "./thumbnails/explore_map.webp";

/** Unwrap CJS interop layers: { default: { default: fn } } → fn */
function unwrap(mod) {
  let v = mod;
  while (v && typeof v !== "function" && v.default) v = v.default;
  return v;
}

const Plot = lazy(async () => {
  const [factoryMod, plotlyMod] = await Promise.all([
    import("react-plotly.js/factory"),
    import("plotly.js-dist-min"),
  ]);
  const factory = unwrap(factoryMod);
  const Plotly = unwrap(plotlyMod);
  return { default: factory(Plotly) };
});

const ForceGraph2D = lazy(async () => {
  const mod = await import("react-force-graph-2d");
  return { default: unwrap(mod) };
});

/* ── Showcase items (flat list with tags) ──────── */
function useShowcaseItems(t) {
  return [
    { id: "bar", tags: ["comparison"], label: t("explore.BarNoteTitle"), shortDesc: t("explore.barShort"), examplePrompt: t("explore.barPrompt"), altNames: t("explore.barAlt"), backend: "plotly", jsonPath: () => import("./examples/bar.json"), noteKey: "explore.BarNote" },
    { id: "line", tags: ["trend"], label: t("explore.LineNoteTitle"), shortDesc: t("explore.lineShort"), examplePrompt: t("explore.linePrompt"), altNames: t("explore.lineAlt"), backend: "plotly", jsonPath: () => import("./examples/line.json"), noteKey: "explore.LineNote" },
    { id: "point", tags: ["correlation"], label: t("explore.PointNoteTitle"), shortDesc: t("explore.pointShort"), examplePrompt: t("explore.pointPrompt"), altNames: t("explore.pointAlt"), backend: "plotly", jsonPath: () => import("./examples/point.json"), noteKey: "explore.PointNote" },
    { id: "histogram", tags: ["distribution"], label: t("explore.HistogramNoteTitle"), shortDesc: t("explore.histogramShort"), examplePrompt: t("explore.histogramPrompt"), altNames: t("explore.histogramAlt"), backend: "plotly", jsonPath: () => import("./examples/histogram.json"), noteKey: "explore.HistogramNote" },
    { id: "box", tags: ["distribution"], label: t("explore.BoxNoteTitle"), shortDesc: t("explore.boxShort"), examplePrompt: t("explore.boxPrompt"), altNames: t("explore.boxAlt"), backend: "plotly", jsonPath: () => import("./examples/box.json"), noteKey: "explore.BoxNote" },
    { id: "violin", tags: ["distribution"], label: t("explore.ViolinNoteTitle"), shortDesc: t("explore.violinShort"), examplePrompt: t("explore.violinPrompt"), altNames: t("explore.violinAlt"), backend: "plotly", jsonPath: () => import("./examples/violin.json"), noteKey: "explore.ViolinNote" },
    { id: "sector", tags: ["composition"], label: t("explore.SectorNoteTitle"), shortDesc: t("explore.sectorShort"), examplePrompt: t("explore.sectorPrompt"), altNames: t("explore.sectorAlt"), backend: "plotly", jsonPath: () => import("./examples/sector.json"), noteKey: "explore.SectorNote" },
    { id: "candle", tags: ["financial", "trend"], label: t("explore.CandleNoteTitle"), shortDesc: t("explore.candleShort"), examplePrompt: t("explore.candlePrompt"), altNames: t("explore.candleAlt"), backend: "plotly", jsonPath: () => import("./examples/candle.json"), noteKey: "explore.CandleNote" },
    { id: "surface", tags: ["spatial", "surface"], label: t("explore.SurfaceNoteTitle"), shortDesc: t("explore.surfaceShort"), examplePrompt: t("explore.surfacePrompt"), altNames: t("explore.surfaceAlt"), backend: "plotly", jsonPath: () => import("./examples/surface3d.json"), noteKey: "explore.SurfaceNote" },
    { id: "unigrid", tags: ["spatial"], label: t("explore.UnigridNoteTitle"), shortDesc: t("explore.unigridShort"), examplePrompt: t("explore.unigridPrompt"), altNames: t("explore.unigridAlt"), backend: "plotly", jsonPath: () => import("./examples/unigrid.json"), noteKey: "explore.UnigridNote" },
    { id: "contour", tags: ["spatial"], label: t("explore.ContourNoteTitle"), shortDesc: t("explore.contourShort"), examplePrompt: t("explore.contourPrompt"), altNames: t("explore.contourAlt"), backend: "plotly", jsonPath: () => import("./examples/contour.json"), noteKey: "explore.ContourNote" },
    { id: "map", tags: ["geographic", "spatial"], label: t("explore.MapNoteTitle"), shortDesc: t("explore.mapShort"), examplePrompt: t("explore.mapPrompt"), altNames: t("explore.mapAlt"), backend: "image", src: mapThumb, noteKey: "explore.MapNote" },
    { id: "graph", tags: ["network"], label: t("explore.GraphNoteTitle"), shortDesc: t("explore.graphShort"), examplePrompt: t("explore.graphPrompt"), altNames: t("explore.graphAlt"), backend: "graph", jsonPath: () => import("./examples/node.json"), noteKey: "explore.GraphNote" },
    { id: "sankey", tags: ["flow"], label: t("explore.SankeyNoteTitle"), shortDesc: t("explore.sankeyShort"), examplePrompt: t("explore.sankeyPrompt"), altNames: t("explore.sankeyAlt"), backend: "plotly", jsonPath: () => import("./examples/sankey.json"), noteKey: "explore.SankeyNote" },
    { id: "parallel", tags: ["multivariate"], label: t("explore.ParallelNoteTitle"), shortDesc: t("explore.parallelShort"), examplePrompt: t("explore.parallelPrompt"), altNames: t("explore.parallelAlt"), backend: "plotly", jsonPath: () => import("./examples/parallel.json"), noteKey: "explore.ParallelNote" },
    { id: "partition", tags: ["hierarchy", "composition"], label: t("explore.PartitionNoteTitle"), shortDesc: t("explore.partitionShort"), examplePrompt: t("explore.partitionPrompt"), altNames: t("explore.partitionAlt"), backend: "plotly", jsonPath: () => import("./examples/partition.json"), noteKey: "explore.PartitionNote" },
    { id: "vector", tags: ["spatial", "flow"], label: t("explore.VectorFieldNoteTitle"), shortDesc: t("explore.vectorShort"), examplePrompt: t("explore.vectorPrompt"), altNames: t("explore.vectorAlt"), backend: "plotly", jsonPath: () => import("./examples/vector.json"), noteKey: "explore.VectorFieldNote" },
    { id: "voxel", tags: ["volumetric", "spatial"], label: t("explore.VolumeRenderingNoteTitle"), shortDesc: t("explore.voxelShort"), examplePrompt: t("explore.voxelPrompt"), altNames: t("explore.voxelAlt"), backend: "image", src: voxel, noteKey: "explore.VolumeRenderingNote" },
  ];
}


export default function Explore() {
  const { t } = useTranslation();
  const allItems = useShowcaseItems(t);
  const allTags = useMemo(() => Array.from(new Set(allItems.flatMap((i) => i.tags))).sort(), [allItems]);

  const galleryRef = useRef(null);
  const toolkitRef = useRef(null);
  const palettesRef = useRef(null);

  const [activeNav, setActiveNav] = useState("gallery");
  const [selected, setSelected] = useState(null);
  const [selectedJson, setSelectedJson] = useState(null);
  const [activeTags, setActiveTags] = useState([]);
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    let items = allItems;
    if (activeTags.length > 0) {
      items = items.filter((i) => activeTags.some((tag) => i.tags.includes(tag)));
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      items = items.filter((i) =>
        i.label.toLowerCase().includes(q) ||
        (i.altNames && i.altNames.toLowerCase().includes(q)) ||
        i.id.toLowerCase().includes(q)
      );
    }
    return items;
  }, [allItems, activeTags, search]);

  const scrollTo = useCallback((ref, key) => {
    setActiveNav(key);
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const openModal = useCallback((item, json) => {
    setSelected(item);
    setSelectedJson(json);
  }, []);

  const closeModal = useCallback(() => {
    setSelected(null);
    setSelectedJson(null);
  }, []);

  useEffect(() => {
    if (!selected) return;
    const handler = (e) => { if (e.key === "Escape") closeModal(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selected, closeModal]);

  return (
    <>
      <SEO
        title={t("seo.exploreTitle")}
        description={t("seo.exploreDescription")}
        url="https://app.nveil.com/explore"
      />
      <div className={styles.pageWrap}>
      <div className={styles.page}>
        <div className={styles.content}>
          {/* Hero */}
          <header className={styles.hero}>
            <h1 className={styles.heroTitle}>{t("explore.heroTitle")}</h1>
            <p className={styles.heroSubtitle}>{t("explore.heroSubtitle")}</p>
            <p className={styles.heroBadge}>{t("explore.heroLibraries")}</p>
          </header>

          {/* Sticky nav */}
          <nav className={styles.sectionNav}>
            <button className={`${styles.navPill} ${activeNav === "gallery" ? styles.active : ""}`} onClick={() => scrollTo(galleryRef, "gallery")}>
              {t("explore.navGallery")}
            </button>
            <button className={`${styles.navPill} ${activeNav === "toolkit" ? styles.active : ""}`} onClick={() => scrollTo(toolkitRef, "toolkit")}>
              {t("explore.navToolkit")}
            </button>
            <button className={`${styles.navPill} ${activeNav === "palettes" ? styles.active : ""}`} onClick={() => scrollTo(palettesRef, "palettes")}>
              {t("explore.navPalettes")}
            </button>
          </nav>

          {/* Gallery */}
          <section>
            <div className={styles.titleRow}>
              <h2 ref={galleryRef} className={styles.sectionTitle}>{t("explore.vizTypes")}</h2>
              <input
                className={styles.searchInput}
                type="text"
                placeholder={t("explore.searchPlaceholder")}
                aria-label={t("explore.searchPlaceholder")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <p className={styles.sectionSubtitle}>{t("explore.vizTypesSubtitle")}</p>
            <div className={styles.filterBar}>
              <div className={styles.tagPills}>
                {allTags.map((tag) => (
                  <button
                    key={tag}
                    className={`${styles.tagPill} ${activeTags.includes(tag) ? styles.tagPillActive : ""}`}
                    onClick={() => setActiveTags((prev) =>
                      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
                    )}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
            <div className={styles.grid}>
              {filtered.map((item, i) => (
                <ShowcaseCard key={item.id} item={item} index={i} onClick={openModal} />
              ))}
              {filtered.length === 0 && (
                <p className={styles.emptyMsg}>{t("explore.noResults")}</p>
              )}
              {filtered.length > 0 && (
                <div className={styles.moreCard}>
                  <h3 className={styles.moreCardTitle}>{t("explore.moreCardTitle")}</h3>
                  <p className={styles.moreCardDesc}>{t("explore.moreCardDesc")}</p>
                </div>
              )}
            </div>
          </section>

          {/* Data Toolkit */}
          <section>
            <h2 ref={toolkitRef} className={styles.sectionTitle}>{t("explore.dataToolkitTitle")}</h2>
            <p className={styles.sectionSubtitle} style={{ marginBottom: 16 }}>
              {t("explore.dataToolkitSubtitle")}
            </p>
            <div className={styles.toolkitShowcase}>
              <img src={choregraph} alt="Kedro pipeline visualization" loading="lazy" className={styles.toolkitShowcaseImg} />
              <div className={styles.toolkitShowcaseText}>
                <h3>{t("explore.toolkitShowcaseTitle")}</h3>
                <p dangerouslySetInnerHTML={{ __html: t("explore.toolkitShowcaseDesc") }} />
              </div>
            </div>
          </section>

          {/* Palettes */}
          <section>
            <h2 ref={palettesRef} className={styles.sectionTitle}>{t("explore.colorPalettes")}</h2>
            <div className={styles.paletteSection}>
              <PaletteGallery onSelect={(p) => console.log("selected:", p)} />
            </div>
          </section>
        </div>

        {/* Detail Modal */}
        {selected && (
          <div className={styles.modalBackdrop} onClick={closeModal}>
            <div className={styles.modal} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
              <button className={styles.modalClose} onClick={closeModal} aria-label="Close">&times;</button>
              <div className={styles.modalPreview}>
                <Suspense fallback={<div className={styles.previewPlaceholder} />}>
                  {selected.backend === "plotly" && selectedJson && (
                    <Plot
                      data={selectedJson.data}
                      layout={{
                        paper_bgcolor: "rgba(0,0,0,0)",
                        plot_bgcolor: "rgba(0,0,0,0)",
                        margin: { l: 50, r: 30, t: 30, b: 50 },
                        font: { color: "#a1a1aa", size: 12 },
                        showlegend: true,
                        legend: { font: { color: "#a1a1aa" } },
                        autosize: true,
                        ...selectedJson.layout,
                        paper_bgcolor: "rgba(0,0,0,0)",
                        plot_bgcolor: "rgba(0,0,0,0)",
                        xaxis: {
                          gridcolor: "rgba(255,255,255,0.03)",
                          zerolinecolor: "rgba(255,255,255,0.03)",
                          ...(selectedJson.layout?.xaxis || {}),
                          gridcolor: "rgba(255,255,255,0.03)",
                          zerolinecolor: "rgba(255,255,255,0.03)",
                        },
                        yaxis: {
                          gridcolor: "rgba(255,255,255,0.03)",
                          zerolinecolor: "rgba(255,255,255,0.03)",
                          ...(selectedJson.layout?.yaxis || {}),
                          gridcolor: "rgba(255,255,255,0.03)",
                          zerolinecolor: "rgba(255,255,255,0.03)",
                        },
                      }}
                      config={{ displayModeBar: true, responsive: true }}
                      useResizeHandler
                      style={{ width: "100%", height: "100%" }}
                    />
                  )}
                  {selected.backend === "graph" && selectedJson && (
                    <ForceGraph2D
                      graphData={selectedJson}
                      width={700}
                      height={400}
                      backgroundColor="rgba(0,0,0,0)"
                      nodeColor={(n) => n.color || "#1b90ba"}
                      linkColor={() => "rgba(255,255,255,0.2)"}
                      nodeRelSize={6}
                      cooldownTicks={100}
                    />
                  )}
                  {selected.backend === "image" && (
                    <img src={selected.src} alt={selected.label} loading="lazy" className={styles.previewImg} />
                  )}
                </Suspense>
              </div>
              <div className={styles.modalBody}>
                <h2 className={styles.modalTitle}>{selected.label}</h2>
                {selected.altNames && <p className={styles.modalAltNames}>{selected.altNames}</p>}
                <p className={styles.modalDesc} dangerouslySetInnerHTML={{ __html: t(selected.noteKey) }} />
                <div className={styles.modalPrompt}>{selected.examplePrompt}</div>
              </div>
            </div>
          </div>
        )}
      </div>
      </div>
    </>
  );
}
