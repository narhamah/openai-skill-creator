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

Output structure:

```text
build/
  my-domain-knowledge/
    SKILL.md
    references/
      index.md
      manifest.json
      <one or more .md files per PDF>
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
