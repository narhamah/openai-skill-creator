# PDF to OpenAI Skill Builder

This repository includes a Python script that converts a folder of PDFs into an upload-ready OpenAI Skill package.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Generate a skill from PDFs

```bash
python pdf_skill_builder.py \
  --pdf-dir /path/to/pdfs \
  --output-dir ./build \
  --skill-name "my-domain-knowledge" \
  --skill-description "Answer questions using the uploaded policy PDFs."
```

Output structure (folder + uploadable zip generated automatically):

```text
build/
  my-domain-knowledge/
    SKILL.md
    references/
      index.md
      manifest.json
      <one or more .md files per PDF>
  my-domain-knowledge.zip
```

## Optional cross-document synthesis with OpenAI

```bash
export OPENAI_API_KEY=...
python pdf_skill_builder.py \
  --pdf-dir /path/to/pdfs \
  --output-dir ./build \
  --skill-name "my-domain-knowledge" \
  --synthesize-with-openai \
  --model gpt-5-mini
```

When enabled, the script writes `references/synthesis.md` with cross-document themes and glossary terms.


## Notes on problematic PDFs

- The extractor now uses a tolerant parser mode (`strict=False`) and skips pages that fail text extraction.
- If one PDF fails entirely, it is skipped and listed in `extraction-warnings.txt` in the generated skill folder.
- If all PDFs fail extraction, the script exits with an error and details.
- If you see `unsupported operand type(s) for +: "float" and "IndirectObject"`, the PDF internals are malformed. Re-save/print that PDF and rerun.

