# share-of-search dashboard

The dashboard renders `snapshot.json` produced by `scripts/sos_calc.py` — it has no
numbers of its own. Most users never build it: `python3 scripts/serve.py` serves the
prebuilt bundle in `dist/`, and `--export` bakes everything into one shareable HTML file.

Only if you want to modify the app:

```bash
npm install
npm run dev      # reads public/snapshot.json
npm run build    # refresh dist/ (committed, so serve.py users get your changes)
```

Stack: Vite + React + TypeScript, Tailwind v4, shadcn/ui, Recharts, Geist.
