# Your website — a step-by-step guide for beginners

This guide assumes you have **never** built a website. Follow the parts in order the first time; afterwards use it as a reference.

**Contents**
0. [What you have](#part-0--what-you-have)
1. [See the site on your own computer](#part-1--see-the-site-on-your-own-computer)
2. [Put it on the internet with GitHub (free)](#part-2--put-it-on-the-internet-with-github-free)
3. [Fill in the things only you know](#part-3--fill-in-the-things-only-you-know)
4. [Day-to-day: add a PhD member, project, grant, publication, news, citations](#part-4--day-to-day-adding-information)
5. [Turn on the heavy demos with Firebase (LLM empathy + EEG)](#part-5--turn-on-the-heavy-demos-with-firebase)
   * 5B. [Sign-in, 5 free minutes and paid minutes (₹1/min)](#part-5b--sign-in-free-minutes-and-paid-minutes)
6. [Lecture and talk videos, and your YouTube channel](#part-6--lecture-and-talk-videos-and-your-youtube-channel)
7. [Add a brand-new page (with a template)](#part-7--add-a-brand-new-page)
8. [Automatic updates — how they work and how to fix them](#part-8--automatic-updates)
9. [Troubleshooting](#part-9--troubleshooting)
10. [What was tested, and what was not](#part-10--what-was-tested-and-what-was-not)

---

## Part 0 — What you have

A **static website**: ordinary files (`.html`, `.css`, `.js`, `.json`) with no database and no server to maintain. GitHub hosts it for free.

```
sudhakar-site/
├── index.html … cv.html      ← the pages (Home, Research, Publications, Teaching, Lab,
│                                Vacancies, Work at a Glance, Talks & Videos, CV)
├── demos/                    ← the 5 interactive programs
│     rl-agent.html  llm-empathy.html  cardiac-webcam.html  affect-webcam.html  eeg-lab.html
├── data/                     ← ★ YOUR INFORMATION LIVES HERE (people, papers, news, videos …)
│     site.json  news.json  members.json  projects.json  grants.json  teaching.json
│     publications_manual.json  publications.json (auto)  metrics.json (auto)
│     talks.json  videos.json  youtube.json (auto)  vacancies.json  …
├── assets/                   ← css (looks), js (behaviour), img (pictures)
├── templates/page-template.html   ← copy this to make a new page
├── scripts/                  ← helper programs (add content, refresh from Google Scholar …)
├── functions/                ← the Firebase backend (only needed for the LLM + EEG demos)
├── .github/workflows/        ← robots that update the site every week
└── GUIDE.md                  ← this file
```

**The one idea to remember:** pages don't contain your content. They read it from the `data/` folder. To change what the site says, you change a file in `data/`, never the HTML.

---

## Part 1 — See the site on your own computer

1. Install **Git**: <https://git-scm.com/downloads>. (Mac: you may already have it — type `git --version` in Terminal.)
2. Install a text editor: **VS Code** <https://code.visualstudio.com>.
3. Open **Terminal** (Mac: Cmd+Space → "Terminal"). Go to the folder and start a tiny web server:

```bash
cd "/Users/vasusud/Documents/Personal Docs/For Website/sudhakar-site"
python3 -m http.server 8123
```

4. In your browser open <http://localhost:8123>. You should see your site. Press `Ctrl+C` in Terminal to stop it.

> Why a server? Browsers refuse to load the `data/*.json` files when you double-click an HTML file. The server fixes that.

---

## Part 2 — Put it on the internet with GitHub (free)

1. Create an account at <https://github.com> (use your institute email if you want the free academic perks).
2. Click **New repository**. Name it either
   * `YOUR-USERNAME.github.io` → your site will be at `https://YOUR-USERNAME.github.io`, **or**
   * anything, e.g. `website` → `https://YOUR-USERNAME.github.io/website`.

   Choose **Public**. Don't tick "Add a README". Click **Create**.
3. In Terminal, from inside `sudhakar-site`:

```bash
git init -b main
git add .
git commit -m "First version of my website"
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
git push -u origin main
```
   (GitHub asks you to log in the first time. If it rejects your password, create a *Personal Access Token* at GitHub → Settings → Developer settings and paste that instead of the password.)
4. On GitHub open the repository → **Settings → Pages**. Under *Build and deployment* choose **Deploy from a branch**, branch **main**, folder **/ (root)**, **Save**. After ~1 minute your site is live at the address shown.
5. **Allow the weekly robots to save changes:** Settings → **Actions → General → Workflow permissions → Read and write permissions → Save**.

**Everyday publishing = three commands** (run inside `sudhakar-site`):

```bash
git add .
git commit -m "Describe what you changed"
git push
```
The site updates about a minute later.

> ⚠️ **Privacy check before your first push.** `Joining Report.pdf` and `PostDoc Work Ex.pdf` are *outside* `sudhakar-site/`, so they are not published. Keep it that way. `.gitignore` also blocks PDFs inside the repo except those in `assets/`.

---

## Part 3 — Fill in the things only you know

Open `data/site.json` in VS Code and edit:

| Field | What to do |
|---|---|
| `email` | Add your institute email, e.g. `"email": "yourname@svnit.ac.in"`. It enables the **Email** button and every **Apply** button on the Vacancies page. (Currently empty so no address is published by accident.) |
| `social.linkedin` | The link you gave (`linkedin.com/feed/`) is your *private feed*, not your profile. Open your LinkedIn profile, copy its address (`https://www.linkedin.com/in/your-handle`) and paste it. Empty = button hidden. |
| `social.github` | Optional. |
| `bio`, `tagline`, `interests` | Rewrite in your own voice. |

**CV button.** Put a PDF at `assets/Sudhakar_Mishra_CV.pdf`; the *Download CV* button appears automatically. Use a version **without your referees' email addresses** — the file will be public.

**Members.** The Lab page currently lists only you. See Part 4 to add students. I listed the co-authors of your three arXiv preprints under *Projects* (they are public on arXiv) but **did not** list them as lab members, since that is their decision and I don't know their status.

**Publications that aren't yours.** Your Google Scholar and OpenAlex profiles contain unrelated papers (poultry genetics, 1990s economics, "Medicinal Trees of India"…), because other people share your name. They are already excluded (see Part 8) — but please check `data/publications_hidden.json`.

Run the checker any time:

```bash
python3 scripts/validate_data.py
```
It tells you in plain English if a comma is missing or an image is not found.

---

## Part 4 — Day-to-day: adding information

There are **three ways**; pick whichever feels comfortable.

* **A. Answer questions in Terminal** — `scripts/manage.py` asks you and writes the file for you (recommended).
* **B. Edit the JSON on GitHub's website** — open the file in your repo, click the ✏️ pencil, edit, *Commit changes*.
* **C. Do nothing** — papers, citation counts and YouTube videos update themselves every Monday (Part 8).

### A. The helper — `scripts/manage.py`

```bash
cd "/Users/vasusud/Documents/Personal Docs/For Website/sudhakar-site"
python3 scripts/manage.py add member        # asks: name, role, period, bio, photo, links, their work
python3 scripts/manage.py add project
python3 scripts/manage.py add grant
python3 scripts/manage.py add publication
python3 scripts/manage.py add news
python3 scripts/manage.py add video         # lecture / talk links
python3 scripts/manage.py add talk
python3 scripts/manage.py add vacancy
python3 scripts/manage.py add alumni
python3 scripts/manage.py list member       # numbered list
python3 scripts/manage.py remove member     # pick a number to delete
python3 scripts/manage.py refresh           # fetch new papers / citations / videos right now
python3 scripts/manage.py check             # validate
```
Then publish with the three git commands from Part 2.

### Recipes (and the JSON, if you prefer editing by hand)

**New PhD student / lab member** — `data/members.json`, inside `"current": [ … ]`:
```json
{
  "name": "Ravi Kumar",
  "role": "PhD Student",
  "period": "2026–present",
  "bio": "EEG microstates of emotion regulation.",
  "photo": "assets/img/members/ravi.jpg",
  "links": { "scholar": "https://scholar.google.com/…", "github": "https://github.com/…" },
  "work": [ { "title": "Microstates in debate practice (poster)", "link": "https://…" } ]
}
```
Put the photo in `assets/img/members/` (create the folder). Members are grouped automatically by `role` ("PhD Student", "Research Intern", …). When someone leaves, move their block into `"alumni": [ … ]`.

**New project** — `data/projects.json`: `{"title": "…", "status": "Ongoing", "area": "…", "summary": "…", "people": ["A","B"], "link": ""}` (it appears on **Research** and **Lab**).

**New grant** — `data/grants.json`: `{"year": "2027", "title": "…", "role": "PI", "agency": "DST-SERB", "note": "₹30 lakh, 3 years"}`.

**New publication.** You don't have to do anything: once it is on your Google Scholar profile, the Monday robot adds it (rules in Part 8). To add one *right now* or with perfect details, run `manage.py add publication` or add to `data/publications_manual.json`:
```json
{ "title": "…", "authors": ["Sudhakar Mishra", "Co Author"], "venue": "IEEE Access 12, 1–10", "year": 2027,
  "type": "journal", "status": "published", "doi": "10.1109/…", "url": "", "featured": true }
```
`type` ∈ journal / conference / preprint / dataset / inprogress / other. `"featured": true` shows it on the Home page. Entries in `publications_manual.json` are never overwritten by the robot and win over automatic ones.

**Citation count / h-index / i10.** Fully automatic: the Monday robot reads your Google Scholar profile and writes `data/metrics.json`, which feeds the numbers and the per-year bar chart on Home and Publications. To refresh immediately: GitHub → **Actions → "Update publications, citations, videos and LLM list" → Run workflow**, or locally `python3 scripts/update_publications.py`. (Today: 220 citations, h-index 8, i10 6.)

**News item** — `manage.py add news` or `data/news.json`: `{"date": "2027-01-15", "text": "Paper accepted at …", "link": ""}`. The 5 newest show on Home.

**Vacancy** — edit `data/vacancies.json`. Each opening has `"status": "open"` or `"closed"`, `topics`, `requirements`, `deadline`. Three openings exist (PhD, Summer intern, Winter intern); change `"open"` to `"closed"` when filled. Add topics as lines in the `topics` list.

**Teaching** — `data/teaching.json` (`current` and `past`). Add lecture notes under a course with `"materials": [{"label": "Slides week 1", "url": "assets/files/rl-week1.pdf"}]`.

> JSON tips: every `{ }` item is separated by a **comma**, but there is **no comma after the last item**. Text is in "double quotes". If you break it, `validate_data.py` (and the Checks robot on GitHub) will tell you which line.

---

## Part 5 — Turn on the heavy demos with Firebase

Three demos run purely in the visitor's browser and need **nothing** here: *Interactive RL agent*, *Cardiac activity from webcam*, *Affective expression profile*.

Two need a server because they do real computation:

| Demo | Needs | Why |
|---|---|---|
| **LLM empathy checker** | Firebase function `empathy_run` | Calls LLM APIs without exposing keys, scores replies |
| **EEG microstate & affect lab** | Firebase function `eeg_analyze` | Runs MNE + scikit-learn on uploaded EEG |

You have Firebase **Blaze** (pay-as-you-go) — required for these. A personal site's usage is normally well inside the free monthly quotas, but **set a budget alert first** (step 7).

### Steps

1. **Install Node.js** (<https://nodejs.org>, "LTS") and **Python 3.12** (you have it). Then in Terminal:
```bash
npm install -g firebase-tools
firebase login
```
2. **Create the project:** <https://console.firebase.google.com> → *Add project* → copy its **Project ID** (e.g. `sudhakar-hcia`). Make sure it's on the **Blaze** plan.
3. **Tell the code your project and your website address.**
```bash
cd "/Users/vasusud/Documents/Personal Docs/For Website/sudhakar-site"
cp functions/.env.example functions/.env
```
   * In `.firebaserc` replace `YOUR-FIREBASE-PROJECT-ID` with your Project ID.
   * In `functions/.env` set `ALLOWED_ORIGINS=https://drsudhakar.github.io` (only the address, **without** `/website` and with no slash at the end; add `,http://localhost:8123` for testing). Only these sites may call your backend.
4. **Create the Python environment** Firebase needs:
```bash
cd functions
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..
```
5. **Get a Hugging Face token** (lets the empathy checker run open models for visitors): <https://huggingface.co/settings/tokens> → *Create new token* → type *Fine-grained* → tick **"Make calls to Inference Providers"**. Then store it as a secret (never in a file):
```bash
firebase functions:secrets:set HF_TOKEN
```
   (paste the token when asked). Hugging Face bills inference to *your* HF account (they give some free monthly credit) — see "Costs" below.
6. **Deploy:**
```bash
firebase deploy --only functions,firestore:rules
```
   (If Terminal says `firebase: command not found`, type `npx firebase-tools` instead of `firebase` in every command.)
   Do **Part 5B steps 1–3 first** (Firestore and sign-in must exist before this deploy). After a few minutes it prints four URLs like `https://empathy-run-xxxx-el.a.run.app`. Copy them into `assets/js/config.js`:
```js
  STATUS_URL:  "https://api-status-xxxx-el.a.run.app",
  EMPATHY_URL: "https://empathy-run-xxxx-el.a.run.app",
  EEG_URL:     "https://eeg-analyze-xxxx-el.a.run.app",
  ACCOUNT_URL: "https://account-xxxx-el.a.run.app",
```
   Then `git add . && git commit -m "Connect backend" && git push`. Open *Work at a glance → LLM empathy checker*: the banner should say "✅ Backend online".
7. **Budget alert (do not skip):** <https://console.cloud.google.com/billing> → *Budgets & alerts* → *Create budget* → e.g. ₹500 / $5 per month with email alerts at 50 % and 100 %.

### How the protections work
* **CORS allow-list** — only your site's address may call the functions.
* **Limits** — `max_instances` (3 empathy, 2 EEG), 12 empathy runs and 10 EEG runs per visitor per hour, ≤ 5 models and ≤ 8 scenarios per run, ≤ 30 MB per EEG upload.
* **Visitor API keys** (paid models) are used for that single request and never stored or logged.
* For stronger protection add Firebase **App Check** (reCAPTCHA) later.

### Costs (rough, check current pricing)
* Functions: a 1–2 minute EEG run uses 4 GB × 2 vCPU ≈ a fraction of a cent. The free tier covers a few hundred of these a month.
* Empathy runs call HF Inference Providers: 5 models × 6 scenarios × (reply + judge) ≈ 60 short calls. Small models cost cents. Visitors who add a *paid* model pay with their own key.

### What the LLM-empathy page does
* **Open-source list** (`data/llm_models.json`) is refreshed weekly with the currently trending Hugging Face chat models that are served live by an inference provider ⇒ *new models appear on their own*. Pin favourites in `data/llm_models_pinned.json` (`["owner/model", …]`).
* A visitor can **type any Hugging Face model name**; the page checks it live on huggingface.co, adds it to the list and remembers it in their browser.
* **Paid models:** choose provider (OpenAI, Anthropic, Google Gemini, Mistral, DeepSeek, Together, OpenRouter), type the model name, paste their key.
* Output: ranking, four 1–5 dimensions + 0–100 overall, every reply with the judge's one-line reason, JSON/CSV export. Change the default judge in `functions/.env` (`DEFAULT_JUDGE_MODEL`) — pick a strong chat model currently listed in `data/llm_models.json`.
* Add or edit scenarios in `functions/empathy_scenarios.json` (then redeploy).

### What the EEG page does
1. Upload one file per task (`.edf .bdf .set .fif .csv .npy`) — or press **demo data**.
2. **Automatic preprocessing:** bad-channel detection + interpolation → notch → band-pass → resample → average reference → artefact-epoch rejection (optional ICA for blinks).
3. **Microstates:** group templates (modified K-means on GFP peaks pooled across tasks; K fixed or chosen automatically), back-fitted to every task → coverage, duration, occurrence, GEV, transition matrices, **task-vs-task statistics** (Mann-Whitney / Kruskal-Wallis, effect sizes, FDR-corrected), task-specific maps and their spatial correlation with the group maps.
4. **Affective computing:** FAA and beta/alpha arousal indices per task, plus cross-validated decoding of the task/condition with **the models you tick**.
5. **Models are tested automatically.** `data/eeg_models.json` is produced by a robot (`.github/workflows/update-eeg-models.yml`) that every week (a) searches Hugging Face for new EEG models, (b) tries to download, load and run each one, and (c) for built-in models checks they train and beat chance on synthetic data. Only models marked **ok** can be ticked. Deep networks (EEGNet, ShallowFBCSPNet, EEG-Conformer) and Hugging Face foundation models (EEGPT, EEG-DINO, NeuroRVQ…) are verified but **run locally** (below), because PyTorch is too heavy for the web service.

**Run EEG locally** (any file size, deep models):
```bash
cd functions
source venv/bin/activate
pip install torch braindecode safetensors      # only for deep models
python -m eeg_tools.cli --list-models
python -m eeg_tools.cli --task "Calm=calm.edf" --task "Fear=fear.edf" --k 4 \
       --models logreg_de riemann_ts_lr eegnet --out result.json
```

**Add your own model:** add one entry to `MODELS` in `functions/eeg_tools/registry.py`, run `python scripts/test_eeg_models.py`; if it says *ok* it shows on the site next deploy.

---

## Part 5B — Sign-in, free minutes and paid minutes

The **LLM empathy checker** and the **EEG lab** are open only to signed-in visitors (Google sign-in):

* Every user gets **5 free minutes per month**.
* All free use on the site shares one **monthly pool** (`FREE_POOL_MINUTES`, default 900 minutes = 15 hours, kept below Google's free tier). When the pool is used up, nobody gets free minutes; visitors see *"This month's quota of free use on this website has been used up. Free minutes return on 1 <next month>."*
* After the free minutes, a box asks *"Continue for ₹1 per minute?"*. The visitor picks the number of minutes, pays to **your UPI QR code**, and types the UPI transaction ID (UTR).
* You confirm the payment on **`admin.html`** and the minutes are added to their balance.
* Nobody can use more than **120 minutes a day**, and each person can run one analysis at a time.
* The time each run takes on the server is what counts. Free minutes are used first.

**Where things are:** the sign-in bar and the payment box appear **at the top of the two demo pages**, and only after the steps below are done. Until then the bar says "Sign-in not set up yet". The approval page is **https://drsudhakar.github.io/website/admin.html**. It is deliberately **not in the menu**: only you need it. Bookmark it.

### Steps (once)
1. **Create the database:** Firebase console → your project → *Build → Firestore Database* → *Create database* → *Production mode* → location **asia-south1 (Mumbai)**.
2. **Turn on Google sign-in:** *Build → Authentication* → *Get started* → *Sign-in method* → **Google** → *Enable* → choose your support e-mail → *Save*. Then go to *Settings → Authorized domains* → *Add domain* → `drsudhakar.github.io`.
3. **Register the website:** gear icon → *Project settings* → *Your apps* → the **`</>` (Web)** button → nickname "website" → *Register app* (no hosting). It shows a `firebaseConfig` block. Copy four values into `assets/js/config.js`:
```js
  FIREBASE: {
    apiKey: "AIza…",
    authDomain: "your-project-id.firebaseapp.com",
    projectId: "your-project-id",
    appId: "1:1234…:web:abcd…",
  },
```
   These values are not secrets; every website that uses Firebase sign-in shows them.
4. **Your QR code:** save the QR image from your UPI app (PhonePe, Google Pay, Paytm, BHIM) as **`assets/img/upi-qr.png`**. Optionally put your UPI ID in `PAYMENT.UPI_ID` in `config.js`; phone users then get a "Pay with a UPI app" button.
5. **Make yourself the admin:** in `functions/.env` set `ADMIN_EMAILS=` your Google e-mail. The other numbers (free minutes, pool, price, daily cap) are in the same file.
6. **Deploy and publish:** run `firebase deploy --only functions,firestore:rules` (Part 5, step 6), paste the four URLs into `config.js`, then:
```bash
git add . && git commit -m "Turn on sign-in and paid minutes" && git push
```

### Approving a payment (each time)
1. Open `admin.html` and sign in with your admin Google account. Use the *Approve payments* button in the bar, or your bookmark.
2. For each row, find the **UPI ref / UTR** in your bank or UPI app. If the amount arrived, click **Approve**. You can change "Minutes to add" first if they paid a different amount. If nothing arrived, click **Reject**.
3. The visitor's balance updates the next time their page loads.

### Changing prices or limits
Edit `functions/.env` (`PRICE_PER_MINUTE_INR`, `FREE_MINUTES_PER_USER`, `FREE_POOL_MINUTES`, `DAILY_CAP_MINUTES`) and run `firebase deploy --only functions` again.

### Good to know
* A plain QR code cannot tell the website that money arrived, so **you approve each payment yourself**. For instant automatic unlocking you would need a payment gateway such as Razorpay.
* Free minutes reset on the 1st of each month (India time). Google's own free tier resets with its billing month, so check *Billing → Reports* now and then and keep the budget alert from Part 5.
* Someone could use several Google accounts to get more free minutes. The shared monthly pool caps what that can cost you.
* Usage is stored in Firestore (`billing_users`, `billing_pool`, `billing_requests`). Browsers cannot read or write it (`firestore.rules`); only your functions can.

---

## Part 6 — Lecture and talk videos, and your YouTube channel

**Your channel** (<https://www.youtube.com/@HCIA26>) is linked in the header buttons and footer. The Monday robot reads its public feed into `data/youtube.json` and shows new uploads under *Talks & Videos → Latest from the HCIA YouTube channel* automatically. (Right now the channel has no uploads of its own, so that section is empty. YouTube only publishes a feed after the first upload.)

**Add a lecture or talk video** — any of these:
```bash
python3 scripts/manage.py add video
```
or add to `data/videos.json`:
```json
{
  "title": "RL Lecture 3 — Temporal-difference learning",
  "url": "https://www.youtube.com/watch?v=XXXXXXXXXXX",
  "type": "Lecture",
  "course": "Reinforcement Learning",
  "date": "2026-09-02",
  "description": "Q-learning and SARSA with the cliff-walking example."
}
```
* `type` can be anything: **Lecture**, **Talk**, **Seminar**, **Tutorial**, **Demo** — videos are grouped by it with a heading each.
* YouTube links of every shape work (`youtube.com/watch?v=`, `youtu.be/`, `/shorts/`, `/live/`). They show a thumbnail and load the player only when clicked (privacy-friendly, `youtube-nocookie`).
* Non-YouTube links (Vimeo, Google Drive, Microsoft Stream, institute server) show as a card with a **Watch ↗** button.
* For **invited talks** with slides, use `data/talks.json` (`"video"` and `"slides"` fields are optional).
* To attach a video to a course: copy its URL into that course's `materials` in `data/teaching.json`.

---

## Part 7 — Add a brand-new page

Example: an **Awards** page.

1. In the folder, copy the template:
```bash
cp templates/page-template.html awards.html
```
2. Open `awards.html` in VS Code and change the three ✏️ spots: `<title>`, the `description`, and the content between the comments. (Write plain HTML — the template shows headings, paragraphs, lists, cards and an image.)
3. Open `assets/js/site.js`, find the `NAV` list near the top and add **one line**:
```js
const NAV = [
  { label: "Home", href: "index.html" },
  …
  { label: "Awards", href: "awards.html" },     // ← new tab
  { label: "CV", href: "cv.html" },
];
```
4. Check at <http://localhost:8123/awards.html> (Part 1), then commit and push (Part 2).

**Page whose content comes from `data/`** (so you can update it without touching HTML): put a list in `data/awards.json`, then ask me — or follow the pattern of `R.grants` in `assets/js/site.js` (a ~10-line function) and use `<div data-render="awards"></div>` in your page.

**A new interactive demo:** put it in `demos/`, copy the `<head>` of `demos/rl-agent.html` (it uses `../assets/…` paths), then add a card to `glance.html`.

---

## Part 8 — Automatic updates

Three robots run on GitHub (free) from `.github/workflows/`. See them under the **Actions** tab; each has a **Run workflow** button.

| Robot | When | What it does |
|---|---|---|
| `update-data.yml` | Mondays + button | Citation metrics, new publications, YouTube videos, open-source LLM list → commits `data/*` |
| `update-eeg-models.yml` | Mondays + when EEG code changes | Finds new EEG models, tests every model, updates `data/eeg_models.json` |
| `checks.yml` | every push | Validates data files and runs all tests |

**How new publications are chosen** (`scripts/update_publications.py`), and why it is careful:
1. Everything in `publications_manual.json` is kept exactly as you wrote it.
2. Papers on your **Google Scholar** profile that are **not** in your list are added automatically, enriched (DOI, venue, authors) from **OpenAlex**.
3. Only papers from **2014 or later** are added (setting `auto_add_min_year` in `data/site.json`) — because name-sharing authors put old papers on your profiles (the log lists what it skipped).
4. Anything whose title is in `data/publications_hidden.json` is never shown. To hide a wrong paper, add its title there.
5. To *fix* an automatic entry (wrong type/venue), copy it into `publications_manual.json` and edit — your version wins.
6. Google Scholar sometimes blocks GitHub's servers. Then the robot keeps the previous metrics and still updates via OpenAlex. Re-run later, or run `python3 scripts/update_publications.py` on your own computer and push.

Optional: add a repository secret `HF_TOKEN` (Settings → Secrets and variables → Actions) so model downloads in the test robot are faster.

---

## Part 9 — Troubleshooting

| Symptom | Fix |
|---|---|
| Page is blank / shows "Could not load" | You opened the file by double-click. Use `python3 -m http.server 8123` (Part 1). |
| Site shows old content after push | Wait 1–2 minutes; hard-refresh (Cmd+Shift+R). Check Actions tab for a red ✗. |
| Red ✗ on "Checks" | Click it → read the message; usually a JSON comma. Run `python3 scripts/validate_data.py`. |
| A tab/section is empty | The matching `data/*.json` is empty or invalid. Run the validator. |
| Backend banner says *not connected* | Fill `assets/js/config.js` (Part 5) and push. |
| *Backend unreachable* | `ALLOWED_ORIGINS` in `functions/.env` must exactly equal your site origin (e.g. `https://you.github.io`); redeploy. |
| Empathy run: "no API key available" | Deploy the `HF_TOKEN` secret (Part 5 step 5) or supply your own key. |
| Camera demos: "camera permission" | The page must be `https://` (GitHub Pages is) or `localhost`; click the camera icon in the address bar → Allow. |
| `git push` rejected | `git pull --rebase` first (the robots commit too), then push again. |
| Photo missing | Check the path in `data/site.json` and that the file exists (`validate_data.py` tells you). |

---

## Part 10 — What was tested, and what was not

**Tested here (all passing):**
* RL agent logic (Q-learning/SARSA/Expected SARSA, reproduces the classic cliff-walking result) — Node tests and in a real browser.
* Heart-rate pipeline (POS + band-pass + peak detection) on synthetic skin-colour signals at 52–130 bpm: spectral error < 0.2 bpm. Expression → emotion scoring on synthetic blendshape inputs.
* LLM-empathy engine with a mocked provider (ranking, error handling, limits, no key leakage). **Not tested against live OpenAI/Anthropic/HF endpoints** (needs real keys).
* EEG pipeline on synthetic EEG with planted microstates: planted maps recovered (spatial correlation > 0.9); between-task differences detected; all web-service models decode the planted difference; CSV upload round-trip.
* Model tester on real downloads: 9/9 built-in models and 4 Hugging Face encoders (EEGPT, EEG-DINO small/medium, NeuroRVQ) ran; 8 other repositories were skipped because they need a custom adapter.
* Live fetches from your Scholar (220 citations, h 8, i10 6 on 12 Nov 2026), OpenAlex, Hugging Face and YouTube.
* All site pages in a browser: rendering, data loading, no console errors.

**Not tested — please check once you are set up:**
* **Webcam demos with a real camera.** I could not use a camera, so the live camera → face landmarks → pulse/expression path was verified only through the maths modules, not end to end. Try both on your laptop first (good light, face still for 30 s).
* **`firebase deploy`.** I don't have your Firebase project, so deployment was not run. The function code was exercised through Flask test clients; the first real deploy may need small fixes (the error messages will say exactly what).
* **Accuracy of webcam heart rate/HRV and of facial "emotion"** on real people. rPPG is sensitive to light, motion and skin tone; HRV from 30 fps video is indicative only; facial movement ≠ felt emotion. The pages say so.
* EEG results are only as valid as the input; the page's p-values treat 2-second epochs as independent (flagged on the page).
