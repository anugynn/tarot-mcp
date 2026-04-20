#!/usr/bin/env python3
"""
Tarot MCP Server

Reads "The Ultimate Guide to Tarot" PDF and returns card meanings
by finding each card's exact section in the book.
"""

import re
import os
from contextlib import asynccontextmanager
from typing import List, Optional, Dict

import pdfplumber
from pydantic import BaseModel, Field, field_validator, ConfigDict
from mcp.server.fastmcp import FastMCP, Context

# ── Constants ────────────────────────────────────────────────────────────────

PDF_PATH = os.environ.get("TAROT_PDF_PATH", "tarot.pdf")

# Canonical card names exactly as they appear in this book
# Key = what we search for in headings, value = display name
CARD_HEADING_MAP = {
    "THE FOOL": "The Fool",
    "THE MAGICIAN": "The Magician",
    "THE HIGH PRIESTESS": "The High Priestess",
    "THE EMPRESS": "The Empress",
    "THE EMPEROR": "The Emperor",
    "THE HIEROPHANT": "The Hierophant",
    "THE LOVERS": "The Lovers",
    "THE CHARIOT": "The Chariot",
    "STRENGTH": "Strength",
    "THE HERMIT": "The Hermit",
    "THE WHEEL OF FORTUNE": "Wheel of Fortune",
    "JUSTICE": "Justice",
    "THE HANGED MAN": "The Hanged Man",
    "DEATH": "Death",
    "TEMPERANCE": "Temperance",
    "THE DEVIL": "The Devil",
    "THE TOWER": "The Tower",
    "THE STAR": "The Star",
    "THE MOON": "The Moon",
    "THE SUN": "The Sun",
    "JUDGMENT": "Judgment",
    "THE WORLD": "The World",
    "THE ACE OF CUPS": "Ace of Cups",
    "THE TWO OF CUPS": "Two of Cups",
    "THE THREE OF CUPS": "Three of Cups",
    "THE FOUR OF CUPS": "Four of Cups",
    "THE FIVE OF CUPS": "Five of Cups",
    "THE SIX OF CUPS": "Six of Cups",
    "THE SEVEN OF CUPS": "Seven of Cups",
    "THE EIGHT OF CUPS": "Eight of Cups",
    "THE NINE OF CUPS": "Nine of Cups",
    "THE TEN OF CUPS": "Ten of Cups",
    "THE PAGE OF CUPS": "Page of Cups",
    "THE KNIGHT OF CUPS": "Knight of Cups",
    "THE QUEEN OF CUPS": "Queen of Cups",
    "THE KING OF CUPS": "King of Cups",
    "THE ACE OF PENTACLES": "Ace of Pentacles",
    "THE TWO OF PENTACLES": "Two of Pentacles",
    "THE THREE OF PENTACLES": "Three of Pentacles",
    "THE FOUR OF PENTACLES": "Four of Pentacles",
    "THE FIVE OF PENTACLES": "Five of Pentacles",
    "THE SIX OF PENTACLES": "Six of Pentacles",
    "THE SEVEN OF PENTACLES": "Seven of Pentacles",
    "THE EIGHT OF PENTACLES": "Eight of Pentacles",
    "THE NINE OF PENTACLES": "Nine of Pentacles",
    "THE TEN OF PENTACLES": "Ten of Pentacles",
    "THE PAGE OF PENTACLES": "Page of Pentacles",
    "THE KNIGHT OF PENTACLES": "Knight of Pentacles",
    "THE QUEEN OF PENTACLES": "Queen of Pentacles",
    "THE KING OF PENTACLES": "King of Pentacles",
    "THE ACE OF SWORDS": "Ace of Swords",
    "THE TWO OF SWORDS": "Two of Swords",
    "THE THREE OF SWORDS": "Three of Swords",
    "THE FOUR OF SWORDS": "Four of Swords",
    "THE FIVE OF SWORDS": "Five of Swords",
    "THE SIX OF SWORDS": "Six of Swords",
    "THE SEVEN OF SWORDS": "Seven of Swords",
    "THE EIGHT OF SWORDS": "Eight of Swords",
    "THE NINE OF SWORDS": "Nine of Swords",
    "THE TEN OF SWORDS": "Ten of Swords",
    "THE PAGE OF SWORDS": "Page of Swords",
    "THE KNIGHT OF SWORDS": "Knight of Swords",
    "THE QUEEN OF SWORDS": "Queen of Swords",
    "THE KING OF SWORDS": "King of Swords",
    "THE ACE OF WANDS": "Ace of Wands",
    "THE TWO OF WANDS": "Two of Wands",
    "THE THREE OF WANDS": "Three of Wands",
    "THE FOUR OF WANDS": "Four of Wands",
    "THE FIVE OF WANDS": "Five of Wands",
    "THE SIX OF WANDS": "Six of Wands",
    "THE SEVEN OF WANDS": "Seven of Wands",
    "THE EIGHT OF WANDS": "Eight of Wands",
    "THE NINE OF WANDS": "Nine of Wands",
    "THE TEN OF WANDS": "Ten of Wands",
    "THE PAGE OF WANDS": "Page of Wands",
    "THE KNIGHT OF WANDS": "Knight of Wands",
    "THE QUEEN OF WANDS": "Queen of Wands",
    "THE KING OF WANDS": "King of Wands",
}

# ── Alias table for flexible user input ──────────────────────────────────────

ALIASES: Dict[str, str] = {}

def _build_aliases() -> None:
    for display in CARD_HEADING_MAP.values():
        lower = display.lower()
        ALIASES[lower] = display
        no_the = lower.removeprefix("the ").strip()
        ALIASES[no_the] = display
        last_word = lower.split()[-1]
        if last_word not in ALIASES:
            ALIASES[last_word] = display
        # e.g. "ace cups" without "of"
        no_of = lower.replace(" of ", " ")
        ALIASES[no_of] = display

_build_aliases()

# ── PDF Parsing ───────────────────────────────────────────────────────────────

def build_card_index(pdf_path: str) -> Dict[str, str]:
    """
    Scan the PDF and map each card display name to its full section text.
    Each section starts with 'UNDERSTANDING [HEADING_KEY]' and ends just
    before the next 'UNDERSTANDING' heading.
    """
    index: Dict[str, str] = {}

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

        # First pass: find start page for each card
        card_start_pages: List[tuple] = []  # (page_index, display_name)

        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
            for line in text.split("\n"):
                clean = line.strip().upper()
                for heading_key, display_name in CARD_HEADING_MAP.items():
                    pattern = f"UNDERSTANDING {heading_key}"
                    if clean == pattern or clean.startswith(pattern + " "):
                        card_start_pages.append((i, display_name))
                        break

        # Second pass: extract text from start to just before next card
        for idx, (start_page_idx, display_name) in enumerate(card_start_pages):
            if idx + 1 < len(card_start_pages):
                end_page_idx = card_start_pages[idx + 1][0]
            else:
                end_page_idx = min(start_page_idx + 12, total_pages)

            pages_text = []
            for pi in range(start_page_idx, end_page_idx):
                t = pdf.pages[pi].extract_text()
                if t:
                    pages_text.append(t.strip())

            index[display_name] = "\n\n".join(pages_text)

    return index


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def app_lifespan(app):
    if not os.path.exists(PDF_PATH):
        raise FileNotFoundError(
            f"PDF not found at '{PDF_PATH}'. "
            "Set the TAROT_PDF_PATH environment variable to the correct path."
        )
    print(f"Loading tarot book from: {PDF_PATH}")
    card_index = build_card_index(PDF_PATH)
    found = sum(1 for v in card_index.values() if v)
    print(f"Ready. Indexed {found}/{len(CARD_HEADING_MAP)} cards.")
    yield {"card_index": card_index}


mcp = FastMCP("tarot_mcp", lifespan=app_lifespan)

# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_card_name(raw: str) -> Optional[str]:
    """Match a user-supplied name to the canonical display name."""
    cleaned = raw.strip().lower()
    if cleaned in ALIASES:
        return ALIASES[cleaned]
    no_the = cleaned.removeprefix("the ").strip()
    if no_the in ALIASES:
        return ALIASES[no_the]
    for display in CARD_HEADING_MAP.values():
        if cleaned in display.lower() or display.lower() in cleaned:
            return display
    return None


def _extract_section(text: str, start_heading: str, end_headings: List[str]) -> str:
    """Extract text between start_heading and the first of end_headings."""
    start_match = re.search(start_heading, text, re.IGNORECASE)
    if not start_match:
        return ""
    content_start = start_match.end()
    end_pos = len(text)
    for eh in end_headings:
        m = re.search(eh, text[content_start:], re.IGNORECASE)
        if m and m.start() < end_pos - content_start:
            end_pos = content_start + m.start()
    return text[content_start:end_pos].strip()


def extract_key_sections(full_text: str) -> str:
    """Pull out the most useful parts of a card's section."""
    end_markers = [
        "REVERSED MEANING", "HIS WISDOM", "HER WISDOM", "ITS WISDOM",
        "THEIR WISDOM", "WISDOM MESSAGE", r"THE \w+ SYMBOLS", "HISTORICAL",
        "TRY A READING",
    ]

    sections = []

    # Description: everything between the heading and UPRIGHT MEANING
    desc_match = re.search(r"UPRIGHT MEANING", full_text, re.IGNORECASE)
    if desc_match:
        raw_desc = full_text[:desc_match.start()].strip()
        lines = raw_desc.split("\n")
        description = "\n".join(lines[1:]).strip()  # skip heading line
        if description:
            sections.append(f"**About this card:**\n{description}")

    upright = _extract_section(full_text, r"UPRIGHT MEANING", end_markers)
    if upright:
        sections.append(f"**Upright Meaning:**\n{upright}")

    reversed_m = _extract_section(full_text, r"REVERSED MEANING", [
        "HIS WISDOM", "HER WISDOM", "ITS WISDOM", "THEIR WISDOM",
        "WISDOM MESSAGE", r"THE \w+ SYMBOLS", "HISTORICAL", "TRY A READING",
    ])
    if reversed_m:
        sections.append(f"**Reversed Meaning:**\n{reversed_m}")

    wisdom = _extract_section(full_text, r"WISDOM MESSAGE", [
        r"THE \w+ SYMBOLS", "HISTORICAL", "TRY A READING", "UNDERSTANDING",
    ])
    if wisdom:
        sections.append(f"**Wisdom Message:** {wisdom}")

    if sections:
        return "\n\n".join(sections)

    # Fallback: first 1500 chars minus the heading line
    lines = full_text.split("\n")
    return "\n".join(lines[1:])[:1500].strip()


# ── Input Models ──────────────────────────────────────────────────────────────

class CardLookupInput(BaseModel):
    """Input for looking up one or more tarot cards."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    cards: List[str] = Field(
        ...,
        description=(
            "List of tarot card names to look up. "
            "Examples: ['The Moon', 'Five of Swords', 'Queen of Cups', 'Death']. "
            "Accepts shorthand like 'moon', 'tower', 'five cups'."
        ),
        min_length=1,
        max_length=10,
    )

    include_full_text: Optional[bool] = Field(
        default=False,
        description=(
            "Set to true to return the complete book section for each card. "
            "Default (false) returns only upright meaning, reversed meaning, and wisdom message."
        ),
    )

    @field_validator("cards")
    @classmethod
    def validate_cards(cls, v: List[str]) -> List[str]:
        cleaned = [c.strip() for c in v if c.strip()]
        if not cleaned:
            raise ValueError("Please provide at least one card name.")
        return cleaned


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool(
    name="tarot_lookup_cards",
    annotations={
        "title": "Look Up Tarot Card Meanings",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def tarot_lookup_cards(params: CardLookupInput, ctx: Context) -> str:
    """
    Look up the meaning of one or more tarot cards from the tarot book.

    Use this when the user tells you which cards they received in a reading.
    Returns the upright meaning, reversed meaning, and wisdom message for
    each card, taken directly from the book's text.

    Args:
        params (CardLookupInput): Input containing:
            - cards (List[str]): Card names to look up (1-10 cards).
            - include_full_text (bool): Return the full book section if true.

    Returns:
        str: Markdown-formatted card meanings sourced from the book.

    Examples:
        - "I got The Moon" -> cards=["The Moon"]
        - "My reading: The Tower, Five of Cups, Queen of Wands"
          -> cards=["The Tower", "Five of Cups", "Queen of Wands"]
        - "moon card" -> cards=["moon"]
    """
    card_index: Dict[str, str] = ctx.request_context.lifespan_state["card_index"]

    results = []
    not_found = []

    for raw_name in params.cards:
        canonical = resolve_card_name(raw_name)
        if canonical is None:
            not_found.append(raw_name)
            continue

        full_text = card_index.get(canonical, "")
        if not full_text:
            not_found.append(raw_name)
            continue

        content = full_text if params.include_full_text else extract_key_sections(full_text)
        results.append(f"# {canonical}\n\n{content}")

    output_parts = list(results)

    if not_found:
        output_parts.append(
            "---\n"
            f"**Could not find:** {', '.join(not_found)}\n\n"
            "Try the full card name like 'The High Priestess' or 'Ten of Pentacles', "
            "or use `tarot_list_cards` to see all available cards."
        )

    return "\n\n---\n\n".join(output_parts) if output_parts else "No cards found."


@mcp.tool(
    name="tarot_list_cards",
    annotations={
        "title": "List All Tarot Cards",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def tarot_list_cards(ctx: Context) -> str:
    """
    List all 78 tarot cards indexed from the book, grouped by suit.

    Use this when the user wants to browse available cards or check
    the correct spelling of a card name.

    Returns:
        str: Markdown list of all cards grouped by Major Arcana and Minor Arcana suits.
    """
    card_index: Dict[str, str] = ctx.request_context.lifespan_state["card_index"]

    major = [
        "The Fool", "The Magician", "The High Priestess", "The Empress",
        "The Emperor", "The Hierophant", "The Lovers", "The Chariot",
        "Strength", "The Hermit", "Wheel of Fortune", "Justice",
        "The Hanged Man", "Death", "Temperance", "The Devil",
        "The Tower", "The Star", "The Moon", "The Sun",
        "Judgment", "The World",
    ]
    suits = {
        "Cups": [n for n in CARD_HEADING_MAP.values() if "Cups" in n],
        "Pentacles": [n for n in CARD_HEADING_MAP.values() if "Pentacles" in n],
        "Swords": [n for n in CARD_HEADING_MAP.values() if "Swords" in n],
        "Wands": [n for n in CARD_HEADING_MAP.values() if "Wands" in n],
    }

    def mark(name: str) -> str:
        return name if card_index.get(name) else f"{name} *(not indexed)*"

    lines = ["# Tarot Cards Available in the Book\n", "## Major Arcana\n"]
    for c in major:
        lines.append(f"- {mark(c)}")

    for suit, cards in suits.items():
        lines.append(f"\n## {suit}\n")
        for c in cards:
            lines.append(f"- {mark(c)}")

    indexed_count = sum(1 for v in card_index.values() if v)
    lines.append(f"\n\n*{indexed_count}/{len(CARD_HEADING_MAP)} cards indexed from the book.*")
    return "\n".join(lines)


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
