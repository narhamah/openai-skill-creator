#!/usr/bin/env python3
"""Build an OpenAI Skill package from a folder of PDFs.

This script extracts text from PDFs, builds structured references, and generates
an upload-ready skill directory that can be zipped and uploaded in the OpenAI
platform Skills storage UI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List



@dataclass
class PdfDocument:
    source_path: Path
    title: str
    page_count: int
    text: str


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "untitled"


def normalize_skill_name(raw: str) -> str:
    name = slugify(raw)
    if len(name) > 63:
        name = name[:63].rstrip("-")
    return name


def find_pdfs(pdf_dir: Path) -> List[Path]:
    return sorted(path for path in pdf_dir.glob("*.pdf") if path.is_file())


def extract_text(pdf_path: Path) -> PdfDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError("pypdf is required. Install with: pip install -r requirements.txt") from exc

    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        clean = text.strip()
        if clean:
            pages.append(f"## Page {i}\n\n{clean}")
    full_text = "\n\n".join(pages).strip()
    return PdfDocument(
        source_path=pdf_path,
        title=pdf_path.stem,
        page_count=len(reader.pages),
        text=full_text,
    )


def chunk_text(text: str, max_chars: int) -> Iterable[str]:
    if len(text) <= max_chars:
        yield text
        return
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split = text.rfind("\n", start, end)
            if split > start + int(max_chars * 0.6):
                end = split
        chunk = text[start:end].strip()
        if chunk:
            yield chunk
        start = end


def build_skill_markdown(
    skill_name: str,
    description: str,
    pdf_docs: list[PdfDocument],
    include_synthesis: bool,
) -> str:
    doc_entries = "\n".join(
        f"- `{doc.source_path.name}` ({doc.page_count} pages)"
        for doc in pdf_docs
    )

    synthesis_section = ""
    if include_synthesis:
        synthesis_section = textwrap.dedent(
            """
            ## Optional synthesis workflow (recommended)

            If `references/synthesis.md` exists, read it before answering complex multi-document questions.
            Use it as a high-level map, then verify details against the per-document references.
            """
        ).strip()

    body = f"""---
name: {skill_name}
description: {description}
---

# {skill_name}

## When to use this skill
Use this skill when the user asks questions that rely on the uploaded PDF corpus.

## Source corpus
{doc_entries}

## Workflow
1. Start with `references/index.md` to see the corpus map.
2. Open the most relevant `references/<doc-name>.md` file(s) based on the user question.
3. If needed, compare findings across multiple references and call out conflicts.
4. In answers, prioritize faithful extraction from the sources and note uncertainty.

{synthesis_section}

## Output guidance
- Cite the document filename(s) used in your reasoning.
- If the corpus does not answer the question, say so explicitly.
- Separate factual extraction from interpretation.
"""
    return body.strip() + "\n"


def write_references(
    references_dir: Path,
    pdf_docs: list[PdfDocument],
    max_chars_per_chunk: int,
) -> None:
    references_dir.mkdir(parents=True, exist_ok=True)

    index_lines = ["# Corpus Index", "", "## Documents", ""]
    manifest = []

    for doc in pdf_docs:
        base_slug = slugify(doc.title)
        chunks = list(chunk_text(doc.text, max_chars_per_chunk)) or [""]
        files = []

        if len(chunks) == 1:
            ref_name = f"{base_slug}.md"
            ref_path = references_dir / ref_name
            ref_path.write_text(
                f"# {doc.title}\n\n"
                f"Source: `{doc.source_path.name}`\n\n"
                f"Pages: {doc.page_count}\n\n"
                f"{chunks[0]}\n",
                encoding="utf-8",
            )
            files.append(ref_name)
        else:
            for idx, chunk in enumerate(chunks, start=1):
                ref_name = f"{base_slug}-part-{idx}.md"
                (references_dir / ref_name).write_text(
                    f"# {doc.title} (Part {idx})\n\n"
                    f"Source: `{doc.source_path.name}`\n\n"
                    f"Pages: {doc.page_count}\n\n"
                    f"{chunk}\n",
                    encoding="utf-8",
                )
                files.append(ref_name)

        manifest.append(
            {
                "source": doc.source_path.name,
                "title": doc.title,
                "pages": doc.page_count,
                "references": files,
                "chars": len(doc.text),
            }
        )
        index_lines.extend(
            [
                f"### {doc.title}",
                f"- Source: `{doc.source_path.name}`",
                f"- Pages: {doc.page_count}",
                f"- Reference files: {', '.join(f'`{f}`' for f in files)}",
                "",
            ]
        )

    (references_dir / "index.md").write_text("\n".join(index_lines).strip() + "\n", encoding="utf-8")
    (references_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def maybe_generate_synthesis(
    references_dir: Path,
    skill_name: str,
    pdf_docs: list[PdfDocument],
    enable: bool,
    model: str,
) -> bool:
    if not enable:
        return False

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[warn] OPENAI_API_KEY not set; skipping synthesis generation.")
        return False

    try:
        from openai import OpenAI
    except ImportError:
        print("[warn] openai package is not installed; skipping synthesis generation.")
        return False

    client = OpenAI(api_key=api_key)

    combined = "\n\n".join(
        f"# {doc.source_path.name}\n{doc.text[:20000]}" for doc in pdf_docs
    )
    prompt = textwrap.dedent(
        f"""
        Build a concise synthesis file for a skill named {skill_name}.
        Use the corpus excerpts below to produce:
        1) key themes,
        2) terminology glossary,
        3) cross-document links,
        4) top ambiguities to verify in source files.

        Keep output under 1,200 words and structure with markdown headings.

        Corpus excerpts:
        {combined}
        """
    )

    response = client.responses.create(model=model, input=prompt)
    text = getattr(response, "output_text", "").strip()
    if not text:
        return False

    (references_dir / "synthesis.md").write_text(text + "\n", encoding="utf-8")
    return True


def create_skill(
    pdf_dir: Path,
    output_dir: Path,
    skill_name: str,
    skill_description: str,
    max_chars_per_chunk: int,
    synthesize: bool,
    model: str,
) -> Path:
    pdf_paths = find_pdfs(pdf_dir)
    if not pdf_paths:
        raise ValueError(f"No PDF files found in {pdf_dir}")

    docs = [extract_text(path) for path in pdf_paths]

    skill_root = output_dir / skill_name
    references_dir = skill_root / "references"
    skill_root.mkdir(parents=True, exist_ok=True)

    write_references(references_dir, docs, max_chars_per_chunk)
    has_synthesis = maybe_generate_synthesis(
        references_dir, skill_name, docs, synthesize, model
    )

    skill_md = build_skill_markdown(skill_name, skill_description, docs, has_synthesis)
    (skill_root / "SKILL.md").write_text(skill_md, encoding="utf-8")

    return skill_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an upload-ready OpenAI skill from a folder of PDFs."
    )
    parser.add_argument("--pdf-dir", required=True, help="Directory containing .pdf files")
    parser.add_argument("--output-dir", default="build", help="Where generated skill folder is written")
    parser.add_argument("--skill-name", required=True, help="Skill name (will be normalized)")
    parser.add_argument(
        "--skill-description",
        default="Use this skill to answer questions from the uploaded PDF corpus.",
        help="Description for SKILL.md frontmatter",
    )
    parser.add_argument(
        "--max-chars-per-chunk",
        type=int,
        default=12000,
        help="Split large extracted text into multiple reference markdown files",
    )
    parser.add_argument(
        "--synthesize-with-openai",
        action="store_true",
        help="Optionally create references/synthesis.md with an OpenAI model",
    )
    parser.add_argument(
        "--model",
        default="gpt-5-mini",
        help="OpenAI model used for synthesis when --synthesize-with-openai is set",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    skill_name = normalize_skill_name(args.skill_name)

    try:
        skill_path = create_skill(
            pdf_dir=Path(args.pdf_dir).resolve(),
            output_dir=Path(args.output_dir).resolve(),
            skill_name=skill_name,
            skill_description=args.skill_description.strip(),
            max_chars_per_chunk=args.max_chars_per_chunk,
            synthesize=args.synthesize_with_openai,
            model=args.model,
        )
    except Exception as exc:
        raise SystemExit(f"[error] {exc}") from exc

    print(f"[ok] Skill created: {skill_path}")
    print("[next] Zip the generated skill directory and upload it in OpenAI Storage > Skills.")


if __name__ == "__main__":
    main()
