import base64
import json
import os
from pydantic import BaseModel, Field

# The OpenAI SDK is an optional runtime dependency: it is only needed when a
# LiteLLM/OpenAI-compatible endpoint is configured (LITELLM_URL). When it is
# missing the app degrades gracefully to rule-based/on-device screening
# instead of crashing at import time (which also keeps the offline test suite,
# Vercel edge runtime, and self-hosted installs without cloud keys working).
try:
    from openai import OpenAI as _OpenAI
except ImportError:  # pragma: no cover - SDK intentionally optional
    _OpenAI = None  # type: ignore[assignment,misc]

_client = None
_GEMINI_CIRCUIT_BROKEN_UNTIL = 0.0

def get_client():
    """Return the cached LiteLLM/OpenAI-compatible client, or None when the
    SDK is not installed or no endpoint is configured."""
    global _client
    if _client is not None:
        return _client

    if _OpenAI is None:
        return None  # openai SDK not installed

    url = (os.getenv("LITELLM_URL") or "").strip()
    if not url:
        return None  # no proxy configured — never dial a hardcoded default

    key = os.getenv("LITELLM_API_KEY", "dummy-key")

    # Tight, bounded transport: a dead or slow proxy must not stall the desk.
    # max_retries=0 stops the SDK's internal retry loop (default 2 retries,
    # each waiting out the full timeout) that turned an absent proxy into a
    # multi-minute "Screening…". 25s is generous for a real local proxy while
    # keeping the desk responsive when one is misconfigured.
    _client = _OpenAI(
        base_url=url,
        api_key=key,
        timeout=25.0,
        max_retries=0,
    )
    return _client

class ExtractedFields(BaseModel):
    name: str | None = Field(description="Holder name extracted from the document", default=None)
    dob: str | None = Field(description="Date of birth in YYYY-MM-DD format", default=None)
    gender: str | None = Field(description="Gender (M, F, etc.)", default=None)
    pan: str | None = Field(description="10-character PAN number if present", default=None)
    driving_licence: str | None = Field(description="Driving licence number if present", default=None)
    passport: str | None = Field(description="Passport or visa number if present", default=None)
    voter_id: str | None = Field(description="Voter ID (EPIC) if present", default=None)
    aadhaar: str | None = Field(description="12-digit Aadhaar number without spaces if present", default=None)

class DiscrepancyResult(BaseModel):
    verdict: str = Field(description="Must be exactly 'CONSISTENT', 'DISCREPANCY', or 'INCOMPLETE'")
    reasoning: str = Field(description="Brief explanation of the verdict, explaining if variations in name/dates are semantic matches or hard mismatches.")
    semantic_match: bool = Field(description="True if all documents semantically refer to the same person despite minor typos or formatting differences.")

def extract_document_data(image_bytes: bytes, doc_type: str = "") -> dict:
    """Uses a multimodal LLM (LiteLLM proxy or direct Gemini Vision) to extract structured fields from a document image."""
    client = get_client()
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    prompt = f"""
    You are an expert Indian & International identity document OCR system.
    Extract the relevant fields from this document image accurately:
    - name: Full name of holder
    - dob: Date of birth (YYYY-MM-DD)
    - gender: M or F
    - pan: 10-character PAN number if this is a PAN card
    - aadhaar: 12-digit Aadhaar number if this is an Aadhaar card
    - driving_licence: DL number if this is a Driving Licence
    - passport: Passport number if this is a passport
    - voter_id: EPIC number if this is a Voter ID
    - address: Full permanent address if printed
    - pincode: 6-digit PIN code if present

    Document type hint: {doc_type or "Unknown"}
    Return only a valid JSON object matching these keys. If a field is not found or not present, set it to null.
    """

    if client:
        try:
            response = client.chat.completions.create(
                model=os.getenv("LITELLM_EXTRACT_MODEL", "gpt-4o"),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_image}"
                                }
                            }
                        ]
                    }
                ],
                response_format={"type": "json_schema", "json_schema": {"name": "ExtractedFields", "schema": ExtractedFields.model_json_schema(), "strict": True}},
                temperature=0.0,
                max_tokens=1024,
            )
            content = response.choices[0].message.content
            if content:
                data = json.loads(content)
                return {"ran": True, "fields": data}
        except Exception as e:
            return {"ran": False, "reason": str(e)}

    global _GEMINI_CIRCUIT_BROKEN_UNTIL
    gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY") or "").strip()
    import time
    if gemini_key and time.monotonic() >= _GEMINI_CIRCUIT_BROKEN_UNTIL:
        try:
            import requests
            for model in ("gemini-2.5-flash", "gemini-1.5-flash"):
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
                body = {
                    "contents": [{
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": "image/jpeg", "data": b64_image}}
                        ]
                    }],
                    "generationConfig": {
                        "response_mime_type": "application/json",
                        "temperature": 0.0,
                        "maxOutputTokens": 1024
                    }
                }
                resp = requests.post(url, json=body, headers={"Content-Type": "application/json"}, timeout=2.5)
                if resp.status_code == 200:
                    payload = resp.json()
                    parts = (payload.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
                    txt = "".join(p.get("text") or "" for p in parts).strip()
                    if txt:
                        parsed = json.loads(txt)
                        return {"ran": True, "fields": parsed, "model": model}
                elif resp.status_code in (400, 401, 403, 404):
                    # Invalid key or unsupported model: trip circuit breaker for 300s
                    _GEMINI_CIRCUIT_BROKEN_UNTIL = time.monotonic() + 300.0
                    break
        except Exception as exc:
            _GEMINI_CIRCUIT_BROKEN_UNTIL = time.monotonic() + 300.0

    return {"ran": False, "reason": "No multimodal LLM backend configured"}

def analyze_session_discrepancies(docs_data: list[dict]) -> dict:
    """Uses an LLM to semantically compare documents in a session for discrepancies.
    Allows minor typos, spelling variations (e.g. Mohd vs Mohammed), or formatting differences.
    """
    client = get_client()
    if not client:
        return {"ran": False, "reason": "LiteLLM proxy not configured"}
        
    prompt = f"""
    You are an expert immigration officer. Analyze the following extracted fields from multiple identity documents presented by a single traveler.
    
    Documents:
    {json.dumps(docs_data, indent=2)}
    
    Determine if these documents belong to the exact same person.
    - Minor spelling variations in transliteration (e.g., Mohd vs Mohammed, Kumar vs Kumar) are OK and should be a SEMANTIC_MATCH.
    - Date format variations or off-by-one-day typos are generally suspicious but might be acceptable if all other fields match perfectly.
    - Completely different names, DOBs, or IDs represent a hard DISCREPANCY.
    - If there is not enough overlapping data (e.g. only 1 document has a name), return INCOMPLETE.
    
    Return your verdict as CONSISTENT, DISCREPANCY, or INCOMPLETE.
    """
    
    try:
        response = client.chat.completions.create(
            model=os.getenv("LITELLM_REASONING_MODEL", "gpt-4o"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {"name": "DiscrepancyResult", "schema": DiscrepancyResult.model_json_schema(), "strict": True}},
            temperature=0.0,
            max_tokens=512,
        )
        content = response.choices[0].message.content
        if content:
            return {"ran": True, "result": json.loads(content)}
        return {"ran": False, "reason": "Empty response"}
    except Exception as e:
        return {"ran": False, "reason": str(e)}
