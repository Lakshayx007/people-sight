// Builds pipeline/assets/deck/template.pptx: the theme (colours and fonts) and the three slide layouts the insight
// deck uses. pipeline/06_build_deck.py fills this template with python-pptx. Only needed to change the look:
//   PPTX_SKILL=<folder with scripts/apply_theme.js> node pipeline/assets/deck/build_template.js   (needs pptxgenjs)
const path = require("path");
const pptxgen = require("pptxgenjs");

const HERE = __dirname;
const THEME = {
  name: "People Sight",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1E2A3A", lt1: "FFFFFF", dk2: "1C2433", lt2: "F3F5F8",
    accent1: "6A2BC2", accent2: "D9472F", accent3: "13866F", accent4: "FFD84D", accent5: "6B7383", accent6: "E6DAFA",
    hlink: "6A2BC2", folHlink: "6B7383",
  },
};

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  pres.title = "People Sight insight deck template";
  pres.author = "Lakshay Malik";
  pres.company = "Porter";

  const footer = { text: "People Sight  ·  Porter People Analytics  ·  data as of 31-Oct-2026 (sample data)",
    options: { x: 0.6, y: 7.08, w: 8.0, h: 0.25, fontSize: 9, color: "8A93A3", margin: 0 } };

  pres.defineSlideMaster({
    title: "Content",
    background: { path: path.join(HERE, "bg_light.png") },
    objects: [
      { placeholder: { options: { name: "eyebrow", type: "body", x: 0.6, y: 0.42, w: 9.0, h: 0.3, fontSize: 11, bold: true,
        color: "6A2BC2", charSpacing: 3, margin: 0, valign: "top", align: "left" }, text: "SECTION" } },
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.72, w: 12.1, h: 0.75, fontSize: 28, bold: true,
        color: "1E2A3A", fontFace: "Cambria", margin: 0, valign: "top", align: "left" }, text: "Headline that states the finding" } },
      { text: footer },
    ],
    slideNumber: { x: 12.33, y: 7.08, w: 0.4, h: 0.25, fontSize: 9, color: "8A93A3", align: "right", margin: 0 },
  });
  pres.defineSlideMaster({
    title: "Opening",
    background: { path: path.join(HERE, "bg_dark.png") },
    objects: [
      { placeholder: { options: { name: "eyebrow", type: "body", x: 0.7, y: 0.75, w: 9.0, h: 0.3, fontSize: 11, bold: true,
        color: "FFD84D", charSpacing: 3, margin: 0, valign: "top", align: "left" }, text: "EYEBROW" } },
      { placeholder: { options: { name: "title", type: "title", x: 0.7, y: 1.25, w: 6.3, h: 2.3, fontSize: 44, bold: true,
        color: "FFFFFF", fontFace: "Cambria", margin: 0, valign: "top", align: "left" }, text: "Deck title" } },
    ],
  });
  pres.defineSlideMaster({
    title: "Closing",
    background: { path: path.join(HERE, "bg_dark.png") },
    objects: [
      { placeholder: { options: { name: "eyebrow", type: "body", x: 0.6, y: 0.42, w: 9.0, h: 0.3, fontSize: 11, bold: true,
        color: "FFD84D", charSpacing: 3, margin: 0, valign: "top", align: "left" }, text: "EYEBROW" } },
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.72, w: 12.1, h: 0.75, fontSize: 28, bold: true,
        color: "FFFFFF", fontFace: "Cambria", margin: 0, valign: "top", align: "left" }, text: "Closing headline" } },
    ],
    slideNumber: { x: 12.33, y: 7.08, w: 0.4, h: 0.25, fontSize: 9, color: "8A93A3", align: "right", margin: 0 },
  });

  // one sample slide per layout (06_build_deck.py removes them before adding its own)
  for (const m of ["Content", "Opening", "Closing"]) pres.addSlide({ masterName: m });
  const out = path.join(HERE, "template.pptx");
  await pres.writeFile({ fileName: out });
  const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");
  await applyTheme(out, THEME);
  console.log("wrote", out);
}

main();
