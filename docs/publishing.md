# Publishing the portfolio site

The local app rebuilds a static site into `site/` and commits it to the `gh-pages` branch after every finished critique or revision, when you toggle a drawing's publish setting, and at startup when the lessons have changed. Publishing never touches your working files, index or current branch. If a GitHub remote is set up it also pushes; until then it just records "not pushed (no remote 'origin')" in the app's footer.

## What becomes public

- Drawings whose publish setting is on (the checkbox at upload, or the Publish/Unpublish button on a critique page), and only versions whose critique finished.
- For each version: the deskewed drawing, the reference photo cropped to what you drew, the critique, rating totals, and revision outcomes.
- Reference photo credit (source link and license).
- The lessons and their git history, plus a "how it works" page.

**Unpublishing** removes a drawing from the live site on the next publish, but earlier versions of the site stay in the `gh-pages` branch history on GitHub (the publisher never force-pushes or rewrites history). Only publish drawings you're comfortable having on record.

Never published: your original phone photos, tool traces, file paths, the judge's reasons, raw clicks, and error details.

## One-time setup

1. Create a **public** repository on GitHub (for example `art-critique`). GitHub Pages is free for public repos.
2. Connect this folder to it and push the code:
   ```bash
   git remote add origin https://github.com/<you>/art-critique.git
   git push -u origin main
   ```
3. Publish once so the `gh-pages` branch exists on GitHub:
   ```bash
   .venv/bin/artcrit publish
   ```
4. On GitHub: **Settings → Pages → Build and deployment → Source: Deploy from a branch**, branch `gh-pages`, folder `/ (root)`.
5. After a minute the site is live at `https://<you>.github.io/art-critique/`.

From then on publishing is automatic while `artcrit serve` runs. To turn it off, start the app with `ARTCRIT_PUBLISH=0`.

## Preview locally

```bash
.venv/bin/python -m http.server 8010 --directory site --bind 127.0.0.1
```
