# Sudhakar Mishra — personal academic website

Static site (HTML/CSS/JS + JSON data) hosted on **GitHub Pages**, with an optional **Firebase** backend for the LLM-empathy and EEG demos.

* **New to this?** Read **[GUIDE.md](GUIDE.md)** — step-by-step, assumes no experience.
* Preview locally: `python3 -m http.server 8123` → <http://localhost:8123>
* Add content: `python3 scripts/manage.py add member|project|grant|publication|news|video|talk|vacancy`
* Refresh from Scholar / YouTube / Hugging Face: `python3 scripts/manage.py refresh`
* Validate: `python3 scripts/validate_data.py`
* Tests: `node tests/test_rl.js && node tests/test_rppg.js && node tests/test_affect.js && (cd functions && python -m pytest tests -q)`

| Tab | Source of its content |
|---|---|
| Home, Research, CV | `data/site.json`, `projects.json`, `grants.json`, `news.json` |
| Publications | `data/publications_manual.json` + automatic (`scripts/update_publications.py`) → `publications.json`, `metrics.json` |
| Teaching | `data/teaching.json` |
| Lab | `data/members.json`, `projects.json` |
| Vacancies | `data/vacancies.json` |
| Work at a Glance | `demos/*.html` (RL agent, LLM empathy, cardiac webcam, expression webcam, EEG lab) |
| Talks & Videos | `data/videos.json`, `talks.json`, `youtube.json` (auto) |

Backend (`functions/`): Python Cloud Functions — `empathy_run`, `eeg_analyze`, `api_status`. EEG code is in `functions/eeg_tools/` and also runs from the command line.
