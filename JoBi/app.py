"""Library book recommender chatbot backend.

Reads your library spreadsheet (LIBRARY.xlsx), embeds each book and online
resource with an open-source model, and recommends what matches the visitor's
message. No LLM and no paid API needed.

Sheets used:
  Books       - the catalogue (title, author, subject, description, tags ...)
  BookCopies  - one row per physical copy; "available" copies are counted as stock
  Resources   - free online material (optional)
Sheets NOT read, on purpose: Loans and Users (student data must never reach a public chatbot).
A plain .csv with a single list of books also works.
"""
import os
import re

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

HERE = os.path.dirname(os.path.abspath(__file__))

# Set HIDE_UNAVAILABLE=1 to hide books whose copies are all issued.
# By default they are still shown, flagged as "all copies issued", and ranked lower.
HIDE_UNAVAILABLE = os.getenv("HIDE_UNAVAILABLE", "0") == "1"


def find_data_file():
    env = os.getenv("BOOKS_FILE")
    if env:
        return env
    for name in ("library.xlsx", "LIBRARY.xlsx", "books.xlsx", "books.xls", "books.csv"):
        path = os.path.join(HERE, name)
        if os.path.exists(path):
            return path
    raise FileNotFoundError("Put your file next to app.py as library.xlsx (or books.csv)")


# Column names can differ; these aliases are matched case-insensitively.
ALIASES = {
    "id": ["id", "bookid"],
    "title": ["title", "book", "book name", "book title", "name"],
    "author": ["author", "writer", "by"],
    "genre": ["subject", "genre", "category"],
    "description": ["description", "summary", "about", "details", "synopsis"],
    "stock": ["stock", "quantity", "qty", "available", "copies", "in stock"],
    "tags": ["tags", "keywords", "tag"],
    "year": ["year", "published", "publication year"],
    "shelf": ["shelf", "shelflocation", "location"],
    "url": ["url", "link"],
    "type": ["type", "format"],
}
TEXT_FIELDS = ["title", "author", "genre", "description", "tags", "year", "shelf", "url", "type"]

model = SentenceTransformer(os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2"))
items = pd.DataFrame()
embeddings = np.zeros((0, 384), dtype="float32")


def normalise(raw):
    """Map whatever column names the sheet uses onto our standard fields."""
    lookup = {str(c).strip().lower(): c for c in raw.columns}
    df = pd.DataFrame(index=raw.index)
    for field, names in ALIASES.items():
        col = next((lookup[n] for n in names if n in lookup), None)
        if col is not None:
            df[field] = raw[col]
        else:
            # No stock column found: treat every item as available.
            df[field] = 1 if field == "stock" else ""
    df["stock"] = pd.to_numeric(df["stock"], errors="coerce").fillna(0)
    for c in TEXT_FIELDS:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df["year"] = df["year"].str.replace(r"\.0$", "", regex=True)
    return df[df["title"] != ""]


def read_sheets(path):
    if path.lower().endswith(".csv"):
        return {"books": pd.read_csv(path)}
    return {str(n).strip().lower(): d for n, d in pd.read_excel(path, sheet_name=None).items()}


def load_books():
    global items, embeddings
    path = find_data_file()
    sheets = read_sheets(path)

    raw = sheets["books"] if "books" in sheets else next(iter(sheets.values()))
    books = normalise(raw)
    books["kind"] = "book"

    # Stock = number of copies marked "available" in the BookCopies sheet.
    copies = sheets.get("bookcopies")
    if copies is not None:
        cl = {str(c).strip().lower(): c for c in copies.columns}
        if "bookid" in cl and "status" in cl:
            cid = pd.to_numeric(copies[cl["bookid"]], errors="coerce")
            status = copies[cl["status"]].astype(str).str.strip().str.lower()
            avail = (status == "available").groupby(cid).sum()
            bid = pd.to_numeric(books["id"], errors="coerce")
            books["stock"] = bid.map(avail).fillna(0)
            if "shelflocation" in cl:
                shelf = copies[cl["shelflocation"]].astype(str).groupby(cid).first()
                books["shelf"] = bid.map(shelf).fillna("")

    parts = [books]
    res = sheets.get("resources")
    if res is not None:
        r = normalise(res)
        r["kind"] = "resource"
        r["stock"] = 1
        r["description"] = np.where(
            r["description"] == "", r["type"] + " (free online resource)", r["description"]
        )
        parts.append(r)

    items = pd.concat(parts, ignore_index=True)
    texts = (
        items["title"] + " by " + items["author"] + ". Subject: " + items["genre"] + ". "
        + items["description"] + " Topics: " + items["tags"].str.replace(",", ", ")
    ).tolist()
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    n_books = int((items["kind"] == "book").sum())
    print(f"Loaded {n_books} books and {len(items) - n_books} resources from {path}")


load_books()

app = FastAPI(title="Library Book Bot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Chat(BaseModel):
    message: str
    k: int = 5


def availability(stock, shelf):
    n = int(stock)
    if n <= 0:
        return "All copies currently issued"
    text = f"{n} cop{'y' if n == 1 else 'ies'} available"
    return f"{text} · Shelf {shelf}" if shelf else text


@app.post("/chat")
def chat(req: Chat):
    q = req.message.strip()
    if not q:
        return {"reply": "Tell me what you want to read or study and I'll suggest books from our library.",
                "books": [], "resources": []}

    qv = model.encode([q], normalize_embeddings=True)[0]
    raw = embeddings @ qv
    kind = items["kind"].values
    stock = items["stock"].values

    # Small boost when the visitor mentions an author (any name part) or a title directly.
    ql = q.lower()
    words = set(re.findall(r"[a-z]{3,}", ql))
    for i in np.where(kind == "book")[0]:
        if words & set(re.findall(r"[a-z]{3,}", items.at[i, "author"].lower())):
            raw[i] += 0.3
        if items.at[i, "title"].lower() in ql:
            raw[i] += 0.15

    rank = raw - np.where((kind == "book") & (stock <= 0), 0.1, 0.0)  # issued books rank lower

    def top(mask, n, floor):
        idx = np.where(mask & (raw > floor))[0]
        return idx[np.argsort(-rank[idx])][:n]

    book_mask = kind == "book"
    if HIDE_UNAVAILABLE:
        book_mask = book_mask & (stock > 0)
    book_idx = top(book_mask, max(1, min(req.k, 10)), 0.15)
    res_idx = top(kind == "resource", 3, 0.2)

    books = [
        {
            "title": items.at[i, "title"],
            "author": items.at[i, "author"],
            "genre": items.at[i, "genre"],
            "year": items.at[i, "year"],
            "availability": availability(items.at[i, "stock"], items.at[i, "shelf"]),
            "available": bool(items.at[i, "stock"] > 0),
            "description": items.at[i, "description"][:160],
        }
        for i in book_idx
    ]
    resources = [
        {
            "title": items.at[i, "title"],
            "type": items.at[i, "type"],
            "genre": items.at[i, "genre"],
            "url": items.at[i, "url"] if items.at[i, "url"].startswith(("http://", "https://")) else "",
        }
        for i in res_idx
    ]

    if not books and not resources:
        return {"reply": "I couldn't find a close match in our library. Try a subject, a topic or an author.",
                "books": [], "resources": []}
    parts = []
    if books:
        parts.append("Here are books from our library that match:")
    if resources:
        parts.append("These free online resources may also help:" if books else
                     "I found no matching books, but these free online resources may help:")
    return {"reply": " ".join(parts), "books": books, "resources": resources}


@app.post("/reload")
def reload_books():
    """Call this after you update the spreadsheet."""
    load_books()
    return {"ok": True, "count": len(items)}


@app.get("/widget.js")
def widget():
    return FileResponse(os.path.join(HERE, "widget.js"), media_type="application/javascript")


@app.get("/")
def demo():
    return FileResponse(os.path.join(HERE, "demo.html"))
