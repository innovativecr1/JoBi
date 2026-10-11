# Library Book Bot: open-source book recommender for your website

Reads `library.xlsx` and suggests books from your library, showing how many copies are available and the shelf location.
It also suggests the free online resources from your `Resources` sheet.
Uses the open-source `all-MiniLM-L6-v2` embedding model (about 90 MB, runs on CPU, no GPU, no paid API, no LLM).

## Run it

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 to try the demo. The first start downloads the model once, so it needs internet access.

## How your spreadsheet is used

| Sheet | Used for |
|---|---|
| `Books` | the catalogue: title, author, subject, year, description, tags |
| `BookCopies` | stock: the number of copies with status `available`, plus the shelf location |
| `Resources` | free online material that is suggested alongside books |
| `Loans`, `Users` | **never read.** They contain student data, which must not reach a public chatbot |

- Books whose copies are all issued are still shown, flagged "All copies currently issued" and ranked lower.
  To hide them completely, start the server with `HIDE_UNAVAILABLE=1`.
- The richer the `description` and `tags` columns are, the better the suggestions.
- After you update the spreadsheet, restart the server or call `POST /reload`.
- A single-sheet `books.csv` (id, title, author, subject, description, tags, optional stock) also works.

## Add it to your website

Paste this before `</body>` on any page (replace the address with your server):

```html
<script src="https://YOUR-SERVER/widget.js" data-api="https://YOUR-SERVER"></script>
```

On WordPress, use a "Custom HTML" block or a header/footer scripts plugin.

## Going live

- Run it on any small VPS (1 GB RAM is enough) behind HTTPS (nginx or Caddy), since a secure site cannot call an HTTP backend.
- In `app.py`, change `allow_origins=["*"]` to your own domain.
- Keep `library.xlsx` on the server only, not in a public web folder.
- Speed: a reply takes milliseconds, because all vectors are computed once at startup.
