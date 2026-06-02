// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// PaletteGallery.jsx — cards with 2 sections + sort + tag filter
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import palettesJson from "../../Explore/ColorPalettes.json";
import {queue } from "../../App";

// ---------- utils ----------
const beautify = (k) => k.replace(/_+/g, " ").replace(/\bVALUES\b/i, "").trim();
const toCss = ([r, g, b, a]) =>
  "#" +
  [r, g, b]
    .map((x) => x.toString(16).padStart(2, "0"))
    .join("")
    .toLowerCase() +
  (a !== undefined && a < 255 ? a.toString(16).padStart(2, "0").toLowerCase() : "");
const by = (sel, dir = "asc") => (a, b) => {
  const av = sel(a), bv = sel(b);
  const r = typeof av === "number" ? av - bv : String(av).localeCompare(String(bv));
  return dir === "asc" ? r : -r;
};

// ---------- data mapping ----------
function usePalettesFromJson(json) {
  return useMemo(() => {
    return Object.entries(json).map(([rawName, v]) => {
      const obj = Array.isArray(v) ? { colors: v } : v ?? {};
      const colors = (obj.colors || []).map(toCss);
      const type = obj.type ?? (colors.length >= 20 ? "continuous" : "discrete");
      const tags = Array.isArray(obj.tags) ? obj.tags : []; // future-proof
      return { name: beautify(rawName), type, colors, count: obj.colors.length, tags };
    });
  }, [json]);
}

// ---------- card ----------
function Card({ p, onSelect }) {
  const colors = Array.isArray(p.colors) ? p.colors : [];
  const tags = Array.isArray(p.tags) ? p.tags : [];
  const isCont = p.type === "continuous";
  const gradient = `linear-gradient(90deg, ${colors.join(",")})`;
  const { t } = useTranslation();
  // Copy all hex values as a space-separated string
  const handleCopyAll = () => {
    navigator.clipboard.writeText(colors.join(" "));
  };

  return (
    <div
      onClick={() => onSelect?.(p)}
      data-tooltip={`${p.name} • ${colors.length} colors`}
      style={{
        borderRadius: 10,
        overflow: "hidden",
        cursor: "pointer",
        background: "#1a1a1a",
        boxShadow: "0 1px 2px rgba(0,0,0,.25), 0 0 0 1px rgba(255,255,255,.06)",
        position: "relative"
      }}
    >
      <div style={{ padding: "8px 10px", fontSize: 13, fontWeight: 700 }}>{p.name}</div>

      {isCont ? (
        <div style={{ height: 56, background: gradient }} />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${colors.length}, 1fr)`, height: 56 }}>
          {colors.map((c, k) => <div key={k} style={{ background: c }} />)}
        </div>
      )}

      {tags.length > 0 && (
        <div style={{ padding: "3px 0px 0px 3px", display: "flex", gap: 6, flexWrap: "wrap" }}>
          {tags.map((tag) => (
            <span
              key={tag}
              style={{
                fontSize: 11,
                background: "#222",
                color: "#60a5fa",
                borderRadius: 6,
                padding: "2px 6px",
                fontWeight: 600,
                letterSpacing: 0.2,
              }}
              aria-label={`Tag: ${tag}`}
            >
              {t("palette.tags." + tag)}
            </span>
          ))}
        </div>
      )}

      <div style={{ padding: 8, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 11, color: "#9ca3af" }}>{colors.length} {t("palette.colors")}</span>
        {/* Clickable hex values container (wraps individual spans) */}
        <div
          style={{
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
            cursor: "pointer",
            background: "#222",
            borderRadius: 6,
            padding: "2px 8px",
            alignItems: "center",
            userSelect: "all",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: 11,
            color: "#e5e7eb",
            position: "relative"
          }}
          data-tooltip="Click to copy all hex values"
          onClick={(e) => {
            e.stopPropagation();
            handleCopyAll();
            queue.add({ title: t("explore.copied"), description: t("explore.palette_copied_to_the_clipboard") }, { timeout: 3000 });
          }}
        >
          {colors.slice(0, 8).map((c, k) => (
            <span
              key={k}
              style={{
                background: "rgb(61 61 61)",
                borderRadius: 6,
                padding: "2px 6px",
                userSelect: "all"
              }}
              data-tooltip={c}
            >
              {c}
            </span>
          ))}
          {colors.length > 8 && <span style={{ color: "#6b7280" }}>+{colors.length - 8}</span>}
        </div>
      </div>
    </div>
  );
}

// ---------- controls ----------
function Controls({ sort, setSort, allTags, activeTags, setActiveTags }) {
  const { t } = useTranslation();
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
      <label style={{ fontSize: 12, color: "#9ca3af" }}>
        {t("palette.sort")}:
        <select
          value={`${sort.key}:${sort.dir}`}
          onChange={(e) => {
            const [key, dir] = e.target.value.split(":");
            setSort({ key, dir });
          }}
          style={{ marginLeft: 8, background: "#1a1a1a", color: "white", borderRadius: 6, padding: "4px 8px", border: "1px solid #333" }}
        >
          <option value="name:asc">A→Z</option>
          <option value="name:desc">Z→A</option>
          <option value="count:asc"># {t("palette.colors")} ↑</option>
          <option value="count:desc"># {t("palette.colors")} ↓</option>
        </select>
      </label>

      {allTags.length > 0 && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, color: "#9ca3af" }}>Tags:</span>
          {allTags.map((tag) => {
            const on = activeTags.includes(tag);
            return (
              <button
                key={tag}
                onClick={() =>
                  setActiveTags((prev) => (on ? prev.filter((x) => x !== tag) : [...prev, tag]))
                }
                style={{
                  fontSize: 12,
                  padding: "4px 8px",
                  borderRadius: 999,
                  border: "1px solid " + (on ? "#60a5fa" : "#333"),
                  background: on ? "rgba(96,165,250,.15)" : "#151515",
                  color: on ? "#bfdbfe" : "#e5e7eb",
                  cursor: "pointer",
                }}
                aria-pressed={on}
                aria-label={`Filter by tag ${tag}`}
              >
                {t("palette.tags." + tag)}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------- section ----------
function Section({ title, items, onSelect }) {
  return (
    <section style={{ marginBottom: 22, width: "100%" }}>
      <div style={{ fontWeight: 800, fontSize: 22, margin: "6px 0 10px" }}>{title}</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 12 }}>
        {items.map((p) => <Card key={p.name + p.count} p={p} onSelect={onSelect} />)}
      </div>
    </section>
  );
}

// ---------- main ----------
export default function PaletteGallery({ palettes, onSelect }) {
  const { t } = useTranslation();
  const data = palettes ?? usePalettesFromJson(palettesJson);

  // sort + filter state
  const [sort, setSort] = useState({ key: "name", dir: "asc" }); // key: "name" | "count"
  const [activeTags, setActiveTags] = useState([]); // array of strings

  // discover all tags from data
  const allTags = useMemo(
    () => Array.from(new Set(data.flatMap((p) => p.tags))).sort((a, b) => a.localeCompare(b)),
    [data]
  );

  // apply filter + sort
  const apply = (list) => {
    const filtered =
      activeTags.length === 0
        ? list
        : list.filter((p) => p.tags && activeTags.every((t) => p.tags.includes(t)));
    // Fix: sort by count as number, not string
    const sel = sort.key === "count" ? (p) => p.count : (p) => p.name;
    return [...filtered].sort(by(sel, sort.dir));
  };

  const discrete = useMemo(() => apply(data.filter((p) => p.type === "discrete")), [data, sort, activeTags]);
  const continuous = useMemo(() => apply(data.filter((p) => p.type === "continuous")), [data, sort, activeTags]);

  // Tag group UI
  const TagGroup = () => (
    activeTags.length > 0 && (
      <div
        role="group"
        aria-label="Active tag filters"
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          marginBottom: 8,
          flexWrap: "wrap"
        }}
      >
        {activeTags.map((tag) => (
          <span
            key={tag}
            style={{
              fontSize: 12,
              background: "#222",
              color: "#60a5fa",
              borderRadius: 6,
              padding: "2px 8px",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
            aria-label={`Active filter: ${tag}`}
          >
            {tag}
            <button
              onClick={() => setActiveTags((prev) => prev.filter((x) => x !== tag))}
              style={{
                marginLeft: 4,
                background: "none",
                border: "none",
                color: "#bfdbfe",
                fontSize: 14,
                cursor: "pointer",
                borderRadius: 4,
                padding: "0 4px"
              }}
              aria-label={`Remove filter ${tag}`}
            >
              ×
            </button>
          </span>
        ))}
        <button
          onClick={() => setActiveTags([])}
          style={{
            fontSize: 12,
            padding: "2px 8px",
            borderRadius: 6,
            border: "1px solid #333",
            background: "#151515",
            color: "#e5e7eb",
            marginLeft: 8,
            cursor: "pointer"
          }}
          aria-label={t("palette.clearFilters")}
        >
          {t("palette.clearFilters")}
        </button>
      </div>
    )
  );


  return (
    <div>
      <Controls sort={sort} setSort={setSort} allTags={allTags} activeTags={activeTags} setActiveTags={setActiveTags} />
      <TagGroup />
    <div style={{
      gap: "45px",
      display: "flex",
      flexDirection: "row",
      justifyContent: "space-around"
    }}>
      <Section title={t("explore.discrete")} items={discrete} onSelect={onSelect}  />
      <Section title={t("explore.continuous")} items={continuous} onSelect={onSelect}  />
    </div>
    </div>
  );
}
