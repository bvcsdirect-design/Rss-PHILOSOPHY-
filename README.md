# Daily Perspectives

Three entries a day for the KLWP wallpaper: one philosophical idea, one question for reflection, and one verified fact. A GitHub Actions workflow picks the day's set each morning (America/Chicago) and publishes a three-item RSS feed on GitHub Pages. It is free and needs no server or API.

```
content/library.json        all entries, with sources and metadata
content/CONTENT.md          the same entries as a readable day-by-day list
config.json                 feed title, time zone, length limits
scripts/generate_feed.py    picks today's set, validates, writes site/feed.xml
tests/                      checks the selection rules and feed validity
state/history.json          which entries ran on which date (kept by the workflow)
.github/workflows/publish.yml  runs daily, commits history, deploys the feed
```

---

## 1. Set up the repository (one time)

1. On GitHub, create a **public** repository named `Rss-PHILOSOPHY-`. Free GitHub Pages needs a public repo.
2. Upload every file from this folder, keeping the folder structure. The `.github/workflows/publish.yml` file is easy to miss because the folder name starts with a dot. If the uploader skips it, use **Add file → Create new file**, type `.github/workflows/publish.yml` as the name, and paste in its contents.
3. Go to **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**.
4. Go to **Actions → Publish daily feed → Run workflow**. Wait for the green check (about a minute).
5. Open `https://bvcsdirect-design.github.io/Rss-PHILOSOPHY-/`. You should see today's three entries and a link to the feed.

Your feed URL is:

```
https://bvcsdirect-design.github.io/Rss-PHILOSOPHY-/feed.xml
```

---

## 2. Connect KLWP

Your theme reads the feed through six text items: `[News] Article A 1/2/3` and `[News] Article B 1/2/3`. The B items are the second set of headlines that the theme's navigation flips to.

1. **Back up first.** In KLWP, open the menu and use **Export** (or save a copy of the preset). Write down the original feed URL: `https://www.cnet.com/rss/news/`.
2. **Pin the six headline formulas** so the navigation can't move them. Replace each formula as follows:

   | Text item | Old formula | New formula |
   |---|---|---|
   | Article A 1 | `$wg(gv(rsslink1), rss, gv(vard01)*3, title)$` | `$wg(gv(rsslink1), rss, 0, title)$` |
   | Article A 2 | `$wg(gv(rsslink1), rss,gv(vard01)*3+1 ,title)$` | `$wg(gv(rsslink1), rss, 1, title)$` |
   | Article A 3 | `$wg(gv(rsslink1), rss,gv(vard01)*3+2, title)$` | `$wg(gv(rsslink1), rss, 2, title)$` |
   | Article B 1 | (whatever it is now) | `$wg(gv(rsslink1), rss, 0, title)$` |
   | Article B 2 | (whatever it is now) | `$wg(gv(rsslink1), rss, 1, title)$` |
   | Article B 3 | (whatever it is now) | `$wg(gv(rsslink1), rss, 2, title)$` |

   Leave `vard01`, the navigation buttons and everything else alone. Navigating now just shows the same three entries.
3. **Change the feed:** in **Globals**, set `rsslink1` to your feed URL from step 1. Save the preset.
4. **Check the line limit.** The CNET headlines are cut off after 2 lines. While editing one Article text item, look for a **Max lines** setting. If raising it from 2 to 3 still fits the spacing, longer entries display in full. If not, keep entries under about 60 characters.

---

## 2b. Or use a KWGT widget (Niagara or any launcher)

`kwgt/daily-perspectives-clip.txt` holds three ready-made layers: the three entries, each with an accent bar.

1. Copy the entire contents of the clip file, starting with `##KUSTOMCLIP##`.
2. Add a KWGT widget to the home screen (4×2 to start), then tap it to open the editor.
3. Tap **+** (top right) → **Komponent**, then immediately press **Back**. KWGT should offer "Paste Komponent from Clipboard". Tap the clipboard icon (top right).
4. Save with the floppy-disk icon.

The feed URL is a setting of the Komponent called "Feed URL". To change it, tap the Daily Perspectives item and open its **Komponent** tab. The `?h=` part makes KWGT fetch the feed fresh every hour.

## 3. What you'll see, and the first-week check

The library holds 90 entries: 30 philosophy, 30 reflection and 30 facts, so you get 30 days with no repeats. About 9% are in Spanish. `content/CONTENT.md` lists every day's set with its sources. After day 30 the cycle starts over, unless you've added a new batch.

The first three days are arranged so each day is longer than the one before. They show where your headline space cuts text off:

| Day | Philosophy | Reflection | Fact |
|---|---|---|---|
| 1 | 63 chars (Pascal) | 40 chars | 39 chars |
| 2 | 87 chars (Ortega, Spanish) | 73 chars | 88 chars |
| 3 | 91 chars (Zhuangzi) | 94 chars | 93 chars |

Most entries are 60–95 characters (median 79). If 3 lines don't fit, tell Claude your limit and the longer entries can be shortened. Check each item:

- [ ] Order is philosophy, then reflection, then fact
- [ ] All three entries are present; none shows "Loading…" or a blank
- [ ] Text fits, or note where it is cut off (this sets the final length limit)
- [ ] The next morning the entries change without you doing anything
- [ ] Tapping navigation doesn't hide anything
- [ ] Still correct after closing and reopening KLWP, and after a restart
- [ ] Accents (é, ó) and the dash (—) display correctly
- [ ] Optional: tapping an entry opens its source link

**If the entries don't change by mid-morning:** check the GitHub Actions run first (section 5). If the run succeeded, KLWP is probably still showing a cached copy. Make the URL change once an hour so KLWP fetches it fresh:

```
$wg(gv(rsslink1) + "?h=" + df(yyyyMMddHH), rss, 0, title)$
```

Do the same with indexes 1 and 2. GitHub ignores the `?h=` part. Only use this if needed, because a new URL has no cached copy if you're offline at that moment.

---

## 4. Adding content

Add entries to `content/library.json`. Each entry needs:

- `id`: unique, e.g. `phil-0004`, `refl-0004`, `fact-0004`
- `category`: `philosophy`, `reflection` or `fact`
- `text`: one line, no hashtags, no emojis
- `lang`: `en` or `es`
- `kind`:
  - philosophy: `verified_quote`, `verified_translation` or `attributed_summary`
  - reflection: `original_question`
  - fact: `verified_fact`
- `approved`: set to `true` only after you've reviewed it. Entries set to `false` are never shown.
- `sources`: required for philosophy and facts. Philosophy also needs `author` and `work`.
- `display_attribution`: optional short name shown after a quote, e.g. `Pascal`.

New entries go at the end. Selection always shows the least-shown entry first, so a new batch plays next with no repeats. When every entry has been shown, the cycle starts again from the beginning. Nothing is ever made up.

Before uploading, you can check your edits on a computer:

```
python scripts/generate_feed.py --check       # validate the library
python scripts/generate_feed.py --preview 30  # see the next 30 days
python scripts/export_content.py              # refresh content/CONTENT.md
```

GitHub also runs these checks on every upload. If something is wrong, the run fails and the previous feed stays online.

---

## 5. Checking it's running and fixing problems

- **Is it running?** Open the repo's **Actions** tab. Each day should show a green run and a commit titled `Daily feed YYYY-MM-DD`.
- **Update manually:** **Actions → Publish daily feed → Run workflow**. This is safe to repeat; the same day always gets the same set.
- **A run failed:** open it and read the red step. "Library problems" lists exactly which entry to fix. The previous feed stays online until it's fixed.
- **Late runs:** GitHub can start scheduled runs late. There are two runs each morning (about 4:17 and 5:47 AM in winter, an hour later in summer). Either one publishes the day's set.
- **Schedule stopped:** GitHub turns off schedules in public repos after 60 days with no activity. The daily history commit counts as activity, so this shouldn't happen. If it does, open Actions, re-enable the workflow and run it.
- **Changing one day's entries:** delete that date's row in `state/history.json`, then run the workflow.

## 6. Restoring the original news feed

In KLWP **Globals**, set `rsslink1` back to `https://www.cnet.com/rss/news/`. To also restore browsing between pages of headlines, import the backup from section 2.
