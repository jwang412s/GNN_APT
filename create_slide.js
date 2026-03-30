const pptxgen = require("pptxgenjs");

let pres = new pptxgen();
pres.layout = "LAYOUT_4x3"; // 10" x 7.5" — poster-style like the reference
pres.author = "TRAIL Team";
pres.title = "TRAIL: Threat Attribution via Intelligence-Linked Graphs";

let slide = pres.addSlide();
slide.background = { color: "FFFFFF" };

// ===== TITLE BAR (gray background with dark red text, matching Waffle) =====
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0, y: 0, w: 10, h: 1.1,
  fill: { color: "D9D9D9" },
  line: { color: "D9D9D9", width: 0 }
});

// Title text
slide.addText("TRAIL: Threat Attribution via Intelligence-Linked Graphs", {
  x: 0.4, y: 0.08, w: 9.2, h: 0.65,
  fontSize: 32, fontFace: "Georgia", bold: true,
  color: "000000", margin: 0
});

// Subtitle
slide.addText("GNN-Based APT Attribution with Hierarchical Classification and LLM Reasoning", {
  x: 0.55, y: 0.7, w: 9, h: 0.35,
  fontSize: 14, fontFace: "Calibri", italic: true,
  color: "333333", margin: 0
});

// ===== LEFT COLUMN =====

// --- Problem and Motivation ---
slide.addText("Problem and Motivation", {
  x: 0.4, y: 1.35, w: 4.5, h: 0.35,
  fontSize: 16, fontFace: "Georgia", bold: true, italic: true,
  color: "990011", margin: 0
});

slide.addText([
  { text: "APT attribution today relies on manual analysis by threat intelligence experts, making it slow, inconsistent, and hard to scale", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
  { text: "Existing automated systems produce flat predictions without calibrated confidence, often overclaiming attribution at the named-actor level", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
  { text: "Threat intelligence data is inherently graph-structured (shared infrastructure, DNS resolution, report co-occurrence) but most tools ignore this topology", options: { bullet: true } }
], {
  x: 0.5, y: 1.75, w: 4.3, h: 2.0,
  fontSize: 11.5, fontFace: "Calibri", color: "222222",
  valign: "top", margin: [0, 0, 0, 4]
});

// --- Goal ---
slide.addText("Goal", {
  x: 0.4, y: 3.95, w: 4.5, h: 0.3,
  fontSize: 16, fontFace: "Georgia", bold: true, italic: true,
  color: "990011", margin: 0
});

slide.addText([
  { text: "Build an end-to-end automated attribution pipeline that ingests raw threat intelligence, constructs a knowledge graph, and produces hierarchical APT predictions with explainable LLM-powered reasoning as a fallback", options: { bullet: true } }
], {
  x: 0.5, y: 4.3, w: 4.3, h: 1.1,
  fontSize: 11.5, fontFace: "Calibri", color: "222222",
  valign: "top", margin: [0, 0, 0, 4]
});

// ===== RIGHT COLUMN =====

// --- Core Innovation ---
slide.addText("Core Innovation", {
  x: 5.2, y: 1.35, w: 4.5, h: 0.35,
  fontSize: 16, fontFace: "Georgia", bold: true, italic: true,
  color: "990011", margin: 0
});

slide.addText([
  { text: "Adopts Palo Alto Unit 42\u2019s tiered attribution framework: Tier 3 (Named Actor) \u2192 Tier 2 (Nation-State) \u2192 Tier 1 (Activity Cluster), reporting confidence-calibrated results instead of overclaiming", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
  { text: "Combines GraphSAGE message-passing with Label Propagation in a weighted ensemble (\u03B1=0.6/0.4) over a heterogeneous knowledge graph (Events, Domains, IPs, URLs, ASNs)", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
  { text: "When GNN+LP confidence falls below threshold, an LLM agent with access to VirusTotal and WHOIS performs multi-step contextual reasoning to refine or override the prediction", options: { bullet: true } }
], {
  x: 5.3, y: 1.75, w: 4.3, h: 2.4,
  fontSize: 11.5, fontFace: "Calibri", color: "222222",
  valign: "top", margin: [0, 0, 0, 4]
});

// ===== ARCHITECTURE DIAGRAM =====

// Phase 1 box (light green)
slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
  x: 5.25, y: 4.45, w: 1.35, h: 1.75,
  fill: { color: "E8F5E9" },
  line: { color: "81C784", width: 1 },
  rectRadius: 0.08
});
slide.addText("Phase 1", {
  x: 5.25, y: 4.48, w: 1.35, h: 0.25,
  fontSize: 9, fontFace: "Calibri", bold: true, color: "2E7D32",
  align: "center", margin: 0
});
slide.addText([
  { text: "OTX Threat\nIntelligence", options: { breakLine: true, fontSize: 8.5 } },
  { text: "\u2193", options: { breakLine: true, fontSize: 10 } },
  { text: "Knowledge\nGraph (Neo4j)", options: { breakLine: true, fontSize: 8.5, bold: true } },
  { text: "\nEvent \u2022 Domain\nIP \u2022 URL \u2022 ASN", options: { fontSize: 7, color: "555555" } }
], {
  x: 5.25, y: 4.75, w: 1.35, h: 1.4,
  fontFace: "Calibri", color: "333333",
  align: "center", valign: "top", margin: 2
});

// Arrow Phase 1 -> Phase 2
slide.addShape(pres.shapes.LINE, {
  x: 6.62, y: 5.32, w: 0.28, h: 0,
  line: { color: "888888", width: 1.5 }
});
// Arrowhead
slide.addText("\u25B6", {
  x: 6.78, y: 5.15, w: 0.3, h: 0.3,
  fontSize: 8, color: "888888", align: "center", valign: "middle", margin: 0
});

// Phase 2 box (light blue)
slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
  x: 6.95, y: 4.45, w: 1.35, h: 1.75,
  fill: { color: "E3F2FD" },
  line: { color: "64B5F6", width: 1 },
  rectRadius: 0.08
});
slide.addText("Phase 2", {
  x: 6.95, y: 4.48, w: 1.35, h: 0.25,
  fontSize: 9, fontFace: "Calibri", bold: true, color: "1565C0",
  align: "center", margin: 0
});
slide.addText([
  { text: "GraphSAGE +\nLabel Propagation", options: { breakLine: true, fontSize: 8.5 } },
  { text: "\u2193", options: { breakLine: true, fontSize: 10 } },
  { text: "Tiered Attribution\n(Unit 42)", options: { breakLine: true, fontSize: 8.5, bold: true } },
  { text: "\nTier 3 \u2192 Tier 2 \u2192 Tier 1", options: { fontSize: 7, color: "555555" } }
], {
  x: 6.95, y: 4.75, w: 1.35, h: 1.4,
  fontFace: "Calibri", color: "333333",
  align: "center", valign: "top", margin: 2
});

// Arrow Phase 2 -> Phase 3
slide.addShape(pres.shapes.LINE, {
  x: 8.32, y: 5.32, w: 0.28, h: 0,
  line: { color: "888888", width: 1.5 }
});
slide.addText("\u25B6", {
  x: 8.48, y: 5.15, w: 0.3, h: 0.3,
  fontSize: 8, color: "888888", align: "center", valign: "middle", margin: 0
});
// "Low confidence?" label
slide.addText("Low\nconfidence?", {
  x: 8.15, y: 4.85, w: 0.7, h: 0.4,
  fontSize: 6.5, fontFace: "Calibri", italic: true, color: "888888",
  align: "center", margin: 0
});

// Phase 3 box (light orange)
slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
  x: 8.65, y: 4.45, w: 1.15, h: 1.75,
  fill: { color: "FFF3E0" },
  line: { color: "FFB74D", width: 1 },
  rectRadius: 0.08
});
slide.addText("Phase 3", {
  x: 8.65, y: 4.48, w: 1.15, h: 0.25,
  fontSize: 9, fontFace: "Calibri", bold: true, color: "E65100",
  align: "center", margin: 0
});
slide.addText([
  { text: "LLM Agent", options: { breakLine: true, fontSize: 8.5, bold: true } },
  { text: "(VirusTotal, WHOIS)", options: { breakLine: true, fontSize: 7 } },
  { text: "\u2193", options: { breakLine: true, fontSize: 10 } },
  { text: "Explainable\nAttribution", options: { fontSize: 8.5, bold: true } }
], {
  x: 8.65, y: 4.75, w: 1.15, h: 1.4,
  fontFace: "Calibri", color: "333333",
  align: "center", valign: "top", margin: 2
});

// ===== SFU BRANDING =====
slide.addText([
  { text: "SFU", options: { bold: true, fontSize: 16, breakLine: true } },
  { text: "SIMON FRASER", options: { fontSize: 7, charSpacing: 2, breakLine: true } },
  { text: "UNIVERSITY", options: { fontSize: 7, charSpacing: 2 } }
], {
  x: 0.3, y: 6.5, w: 1.5, h: 0.85,
  fontFace: "Calibri", color: "990011",
  valign: "top", margin: 0
});

// ===== SAVE =====
pres.writeFile({ fileName: "/Users/jwang/MASTER_CAPSTONE/TRAIL_Project_Slide.pptx" })
  .then(() => console.log("Created TRAIL_Project_Slide.pptx"))
  .catch(err => console.error(err));
