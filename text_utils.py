"""Shared text cleanup for generated emails (dash stripping, comma spacing)."""

import re


def clean_email_text(text: str) -> str:
    # Em/en dashes used as sentence separators become commas. Handle the
    # padded case first so we don't leave a stray space before the comma
    # (e.g. "science — placed" must become "science, placed", not "science , placed").
    text = text.replace(" — ", ", ").replace("—", ", ")
    text = text.replace(" – ", ", ").replace("–", ", ")
    text = text.replace(" → ", " to ").replace("→", " to ")

    # General comma-spacing normalizer, in case the model (or the dash
    # substitution above) leaves commas misspaced anywhere else.
    text = re.sub(r"[ \t]+,", ",", text)  # no space before a comma
    text = re.sub(r"(\d),(\d)", r"\1<COMMA>\2", text)  # protect "1,000"-style grouping
    text = re.sub(r",(?!\s|$)", ", ", text)  # ensure one space after a comma
    text = text.replace("<COMMA>", ",")

    return text
