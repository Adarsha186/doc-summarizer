import os
import tempfile
import functions_framework
import google.generativeai as genai
from google.cloud import storage, secretmanager
from google.oauth2 import service_account
from pypdf import PdfReader

GCP_PROJECT_ID = "secret-timing-460814-i4"
SOURCE_BUCKET = "pdf_summarize"
SOURCE_PREFIX = "pdfs/"
DEST_BUCKET = "pdf_summarize_results"
DEST_PREFIX = "summaries/"


def access_secret(secret_name: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    project_id = GCP_PROJECT_ID
    secret_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": secret_path})
    return response.payload.data.decode("UTF-8")


GOOGLE_API_KEY = access_secret("GOOGLE_API_KEY")

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

storage_client = storage.Client(project=GCP_PROJECT_ID)
src_bucket = storage_client.bucket(SOURCE_BUCKET)
dest_bucket = storage_client.bucket(DEST_BUCKET)


def extract_text_from_pdf(path: str) -> tuple[str, int]:
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages), len(reader.pages)


# --- replace summarize_text -----------------------------
def summarize_text(raw_text: str, pages: int) -> str:
    prompt = f"""You are an *expert document summarizer*.

                Summarize the document below using **exactly** this structure:

                **Topic / Subject** – one sentence  
                **Length** – “{pages} pages, approx {{word_count}} words”  
                **Important Points** – 3-8 short bullets  
                **Key Take-aways** – 1-3 lines on why the doc matters

                --- BEGIN DOCUMENT ---
                {raw_text}
                --- END DOCUMENT ---
            """

    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.2,
            "max_output_tokens": 512
        }
    )
    return response.text


@functions_framework.cloud_event
def summarize_pdf_gcs_trigger(cloud_event):
    print(cloud_event)
    event_data = cloud_event.data
    file_name = event_data.get('name')
    if not file_name.endswith(".pdf"):
        print(f"Skipped non-PDF: {file_name}")
        return

    bucket = storage_client.bucket(event_data.get('bucket'))
    blob = bucket.blob(file_name)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        blob.download_to_filename(tmp.name)
        print(f"Downloaded {file_name} to {tmp.name}")

        pdf_text, page_count = extract_text_from_pdf(tmp.name)
        summary = summarize_text(pdf_text, page_count)

        base_name = os.path.splitext(os.path.basename(file_name))[0]
        dest_blob_name = f"{DEST_PREFIX}{base_name}_summary.md"
        dest_bucket.blob(dest_blob_name).upload_from_string(
            summary, content_type="application/markdown"
        )
        print(f"Uploaded gs://{DEST_BUCKET}/{dest_blob_name}")

    return "Cloud func executed"