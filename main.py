import google.generativeai as genai
import os
from pathlib import Path
from pypdf import PdfReader
from google.cloud import storage
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()

SOURCE_BUCKET = "pdf_summarize"
SOURCE_PREFIX = "pdfs/"
DEST_BUCKET = "pdf_summarize_results"
DEST_PREFIX = "summaries/"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_SA_KEY = os.getenv("GOOGLE_SA_KEY")

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


creds = service_account.Credentials.from_service_account_file(GOOGLE_SA_KEY)
storage_client = storage.Client(credentials=creds, project=creds.project_id)
src_bucket = storage_client.bucket(SOURCE_BUCKET)
dest_bucket = storage_client.bucket(DEST_BUCKET)

def extract_with_pypdf(path: str) -> tuple[str, int]:
    reader = PdfReader(path)
    pages  = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages), len(reader.pages)

# --- replace summarize_text -----------------------------
def summarize_text(raw_text: str, pages: int) -> str:
    """
    Ask Gemini to produce a structured summary.
    Uses a single user prompt; no unsupported 'system' role.
    """
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
# ---------------------------------------------------------




def process_blob(blob):
    local_pdf = blob.name.split("/")[-1]
    blob.download_to_filename(local_pdf)
    print(f"Extracting file: {blob.name}")

    # ⬇️  unpack both values
    pdf_text, page_count = extract_with_pypdf(local_pdf)

    summary = summarize_text(pdf_text, page_count)

    base_name       = os.path.splitext(local_pdf)[0]
    dest_blob_name  = f"{DEST_PREFIX}{base_name}_summary.json"
    dest_bucket.blob(dest_blob_name).upload_from_string(
        summary, content_type="application/json"
    )
    print(f"Uploaded gs://{DEST_BUCKET}/{dest_blob_name}")
    os.remove(local_pdf)

    console_url = (
        "https://console.cloud.google.com/storage/browser/_details/"
        f"{DEST_BUCKET}/{dest_blob_name}"
    )
    print(f"Console link: {console_url}")



if __name__ == "__main__":
    pdf_blobs = [
        b for b in src_bucket.list_blobs(prefix=SOURCE_PREFIX)
        if b.name.lower().endswith(".pdf")
    ]

    if not pdf_blobs:
        print("No PDF files found.")
    else:
        for blob in pdf_blobs:
            try:
                process_blob(blob)
            except Exception as e:
                print(f"Failed on {blob.name}: {e}")