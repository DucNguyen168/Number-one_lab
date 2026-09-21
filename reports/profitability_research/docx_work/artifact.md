# Template execution contract

- Reference: `C:\Users\Admin\.codex\plugins\cache\openai-curated-remote\openai-templates\0.1.1\skills\artifact-template-legal-memorandum\assets\reference.docx`
- SHA-256: `D3006F9074E46823D103FE283BE19901F55F75C19811558455D7A16C61797355`
- Reference render: unavailable because `soffice.exe` is not installed or on PATH. The retained `assets/preview.png` was inspected at original resolution. Page count is unresolved. The document has one section and one recurring page pattern.
- Evidence: `template-style-evidence.json`, `section_audit.py` console output, package-part SHA inventory, paragraph/run inspection, and `assets/preview.png`.

## Page system

- US Letter portrait, 8.5 x 11 inches; one section; one column.
- Margins: 1 inch on every side. New-page section start.
- Header and footer are not linked to a previous section. No different first page and no odd/even variation.
- Header is a centered, small, light gray all-caps designation. Replace its legal placeholder with a neutral research-report label.
- Footer contains the page-number furniture and must be preserved.

## Typography and components

- Main display face: embedded Play bold, centered, black. The output title must use Word `Title` style while retaining the template's visual character.
- Body face: embedded Garamond, approximately 10.5–11 pt, black, justified with first-line indents for prose.
- Section headings: centered, bold, underlined Garamond in the reference. The output will reuse this treatment through Word heading styles so the longer report has a usable outline.
- Metadata block uses bold short labels followed by tab-aligned values.
- A thin horizontal rule follows metadata. It is separated from the title by the metadata block.
- Numbered items use the retained numbering definitions and hanging-indent rhythm.
- New tables may use the Garamond body system, dark header fill, white header text, narrow cell margins, and restrained borders. They must stay within the 6.5-inch text width.

## Content flow and slot map

- `word/header1.xml`: replace the legal confidentiality placeholder with `BÁO CÁO NGHIÊN CỨU · 05/09/2026`; preserve its layout.
- `word/footer1.xml`: preserve unchanged, including page numbering.
- `word/document.xml`: replace the legal title, recipient metadata, background, analysis, and conclusion placeholders with the research title, scope, evidence, detailed experimental plan, decision gates, and sources.
- The legal-memo content slots do not have enough capacity. Clone the reference's body paragraph, centered heading, metadata, numbered-list and rule patterns as needed. Preserve page geometry, font system, header/footer, embedded fonts, theme, numbering, and relationships.

## Package preservation and fidelity gates

- Preserve all package parts except `word/document.xml`, `word/header1.xml`, `word/styles.xml`, and `[Content_Types].xml`/relationships if required by newly inserted hyperlinks.
- Preserve embedded fonts, theme, numbering, footer, page geometry, and section count.
- Final structural audits must confirm one section, Letter portrait, 1-inch margins, intact footer/page field, valid headings, valid hyperlinks, no placeholder legal text, and readable tables.
- Visual rendering is required by the document workflow but may remain unavailable on this Windows host because neither bundled nor installed LibreOffice exists. If still unavailable after diagnosis, deliver with structural QA and disclose the limitation.
