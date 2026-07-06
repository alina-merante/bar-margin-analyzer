import os
import json
from typing import Optional, Dict

def parse_invoice_with_llm(text: str) -> Optional[Dict[str, str]]:
    """If OPENAI_API_KEY is set, call OpenAI to parse invoice text into structured fields.

    Returns a dict with keys: supplier, invoice_number, issue_date, due_date, total, vat
    or None if no API key is configured or parsing failed.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        import openai
    except Exception:
        return None

    openai.api_key = api_key
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    system = (
        "You are a precise invoice parser. Extract the following fields from the provided OCR'd invoice text: "
        "supplier, invoice_number, issue_date (ISO yyyy-mm-dd if possible), due_date (ISO), total, vat. "
        "Return ONLY a valid JSON object with these keys. Use empty string if a field is missing. Do not add any commentary."
    )

    # Few-shot examples to improve robustness
    example1_user = (
        "OCR TEXT:\n"
        "Casa del Caffè Vergnano S.p.A.\n"
        "Fattura n. 000123\n"
        "Data: 15/03/2026\n"
        "Scadenza: 15/04/2026\n"
        "Totale: 1.234,56 EUR\n"
        "Imposta: 234,56"
    )
    example1_assistant = (
        '{"supplier":"Casa del Caffè Vergnano S.p.A.", "invoice_number":"000123", "issue_date":"2026-03-15", "due_date":"2026-04-15", "total":"1234.56", "vat":"234.56"}'
    )

    example2_user = (
        "OCR TEXT:\n"
        "Spett.le Ristorante Rossi\n"
        "Numero fattura: F-98765\n"
        "Data fattura 01-02-26\n"
        "Totale documento 250,00\n"
        "IVA 0"
    )
    example2_assistant = (
        '{"supplier":"Ristorante Rossi", "invoice_number":"F-98765", "issue_date":"2026-02-01", "due_date":"", "total":"250.00", "vat":"0"}'
    )

    user = "OCR TEXT:\n" + text

    try:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": example1_user},
                {"role": "assistant", "content": example1_assistant},
                {"role": "user", "content": example2_user},
                {"role": "assistant", "content": example2_assistant},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=800,
        )

        content = resp["choices"][0]["message"]["content"].strip()

        # attempt to extract JSON from the output
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            return None

        json_text = content[start:end+1]
        parsed = json.loads(json_text)

        # ensure all keys exist
        result = {
            "supplier": parsed.get("supplier", "").strip(),
            "invoice_number": parsed.get("invoice_number", "").strip(),
            "issue_date": parsed.get("issue_date", "").strip(),
            "due_date": parsed.get("due_date", "").strip(),
            "total": parsed.get("total", "").strip(),
            "vat": parsed.get("vat", "").strip(),
        }

        return result

    except Exception:
        return None
