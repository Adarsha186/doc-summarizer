# PDF Summarizer Pipeline

A Python utility that pulls PDFs from a **source Google Cloud Storage bucket**, summarizes each document with **Gemini 1.5‑Flash**, and pushes the structured summaries (JSON) into a **destination bucket**.

---

## 1 . Prerequisites

| Tool / Service       | Required Version                                                                                        | Purpose                   |
| -------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------- |
| Python               | 3.9 – 3.12                                                                                              | Runtime language          |
| `pip` packages       | `google-cloud-storage`, `google-auth`, `google-generativeai`, `pypdf`, `python-dotenv`                  | Core deps                 |
| Google Cloud project | Billing enabled                                                                                         | Buckets & service account |
| Service Account      | Roles: **Storage Object Viewer** on *source* bucket, **Storage Object Creator** on *destination* bucket | Auth                      |

> **Tip — Local dev only:** Install the [Cloud SDK](https://cloud.google.com/sdk) so you can run `gsutil` & `gcloud` commands.

---

## 2 . One‑time Cloud setup

1. **Create buckets**

   ```bash
   gsutil mb gs://pdf_summarize           # source
   gsutil mb gs://pdf_summarize_results   # destination

   # optional “sub‑folders” (GCS is flat, but prefixes help)
   gsutil cp -n dummy.pdf gs://pdf_summarize/pdfs/
   ```
2. **Service account**

   * Console → **IAM & Admin → Service Accounts** → New → `pdf-summarizer-sa`
   * Add roles:

     * **Storage Object Viewer** (source bucket scope)
     * **Storage Object Creator** (destination bucket scope)
   * **Key** → `Create key → JSON` → save locally (e.g. `service_key.json`).

---

## 3 . Local installation

```bash
python -m venv venv
source venv/bin/activate               # Windows: venv\Scripts\activate
pip install -r requirements.txt        # see below

# .env (create in project root)
GOOGLE_API_KEY=ai-XXXXXXXXXXXXXXXXXXXX
GOOGLE_SA_KEY=/abs/path/to/service_key.json
```

**`requirements.txt`**

```text
google-cloud-storage
google-generativeai
pypdf
python-dotenv
```

---

## 4 . Code walkthrough (`main.py`)

| Section                    | What it does                                                                                                                                            |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Env load**               | Reads `GOOGLE_API_KEY` & `GOOGLE_SA_KEY` from `.env`.                                                                                                   |
| **Client setup**           | – `genai.configure()` builds the Gemini client.<br>– `storage.Client()` uses the service‑account key for both buckets.                                  |
| **`extract_with_pypdf()`** | Returns `(full_text, page_count)` for each PDF.                                                                                                         |
| **`summarize_text()`**     | Sends a single prompt to Gemini 1.5‑Flash. Output is **structured markdown** containing Topic, Length, Important Points, Key Take‑aways.                |
| **`process_blob()`**       | *For each blob*: download → extract → summarize → upload JSON to `gs://pdf_summarize_results/summaries/<name>_summary.json` → clean‑up local temp file. |
| **Main loop**              | Lists all objects under `pdfs/` prefix that end in `.pdf` and calls `process_blob()` in sequence.                                                       |

## 5 . Run locally

```bash
python main.py
```

Console output resembles:

```text
Extracting file: pdfs/Report.pdf
Uploaded gs://pdf_summarize_results/summaries/Report_summary.json
Console link: https://console.cloud.google.com/storage/browser/_details/pdf_summarize_results/summaries/Report_summary.json
```

---

## 6 . Deploy to Cloud Run (optional)

```bash
gcloud run deploy pdf-summarizer \
  --source=. \
  --region=YOUR_REGION \
  --service-account=pdf-summarizer-sa@PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars=GOOGLE_API_KEY=ai-XXXXXXXXXXXX \
  --execution-environment=gen2
```

* Use `/tmp` for temporary downloads; code already does this implicitly on Cloud Run.
* No JSON key file is required at runtime; Cloud Run injects the service‑account identity.

---

## 7 . Troubleshooting

| Symptom                                         | Likely fix                                                                              |
| ----------------------------------------------- | --------------------------------------------------------------------------------------- |
| `DefaultCredentialsError`                       | `.env` path wrong *or* key lacks Storage roles.                                         |
| `403 Forbidden` on upload                       | Check **Storage Object Creator** on destination bucket.                                 |
| `400 Content with system role is not supported` | Flash model doesn’t accept `"system"` role; use single‑prompt format (already done).    |
| Empty `pdf_blobs` list                          | Wrong `SOURCE_PREFIX` – inspect object names with `gsutil ls -r gs://pdf_summarize/**`. |

---

## 8 . Extending

* **Batch concurrency** – wrap `process_blob()` in `concurrent.futures.ThreadPoolExecutor` for parallel runs.
* **Vertex AI** – swap `google-generativeai` for `vertexai.preview.generative_models` if you prefer an on‑GCP endpoint.
* **Error reporting** – push failures to Cloud Logging or Slack webhook.

---
