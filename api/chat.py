"""POST /api/v1/chat: pytania o wybrane miejsce KsiÄ™Å¼yca i jego analogi (Gemini, streaming SSE).

Klucz i model z ``.env`` (GOOGLE_API_KEY, GEMINI_MODEL). Kontekst skÅ‚ada backend z ``service.analogs`` razem
z danymi practicality/constraints, wiÄ™c front wysyÅ‚a tylko identyfikatory i historiÄ™ rozmowy.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import Field

from . import service
from .schemas import AnalogsRequest, ErrorResponse, Model, MoonQuery

load_dotenv()

DEFAULT_MODEL = "gemini-3.1-flash-lite"
MAX_HISTORY = 12
MAX_MESSAGE_CHARS = 2000

# Te same staÅ‚e wagi, co na froncie (api.ts): teren 0.6, zakres temperatur 0.2, oÅ›wietlenie 0.2.
CONTEXT_REQUEST = dict(top_k=5, max_per_region=1, w_thermal=0.2, w_illum=0.2, include_practicality=True)

SYSTEM_PROMPT = """\
You are the analyst built into "Space Twin", an app that finds Earth places whose terrain resembles a chosen place on the Moon, \
so that lunar missions can be rehearsed on Earth. You talk to a curious non-expert (a judge, a student, a mission planner).

RULES
- Answer only from the DATA block below and the glossary. Never invent numbers, places, missions, dates or sources.
- Quote the exact numbers from the data with units (e.g. "slope p50 8.2Â° vs 7.9Â°", "283 K swing", "94% sunlit"), rounded sensibly and given once (scores to whole numbers, other values to 1-2 decimals; never "80 (79.95)").
- If something is not in the data, say "That isn't in the data I have." and, if useful, mention what is.
- Questions unrelated to this Moon site, its Earth matches or how the matching works: politely decline in one sentence and suggest two things you can answer.
- Reply in English, concisely: 2-5 short sentences or a short bullet list. Use **bold** only for place names.
- Refer to matches as "#1 Name". The user sees the same five matches in the app. Use plain words instead of field names (say "land rights", not community_rights_status).
- Be honest about uncertainty: say when a value is estimated, missing or only a proxy.

GLOSSARY
- Match ranking = terrain similarity (60%), day-night temperature swing (20%), sunlit share of daytime (20%). Distance: smaller = more similar. \
Quality labels: good (<0.5), moderate (<1.0), poor.
- Moon and Earth temperature swings come from different instruments (Diviner vs MODIS) and are NOT comparable in kelvin; the ranking compares percentiles within each body.
- solar_visibility_fraction = share of the daytime the terrain does not block the Sun.
- Minerals: Moon values come from orbital spectra; Earth values are estimates from rock type (lithology), not measurements. "other" is Earth-only.
- Practicality (Earth only, never changes the ranking): scores 0-100, higher = easier/cheaper. access, buildability, emergency_support, infrastructure, population. \
isolation_logistics_penalty and population_impact_penalty are 0-100, higher = worse. field_campaign_score is for a short field campaign; \
facility_score for a permanent facility. Cost classes: LOW (>=75), MEDIUM (>=50), HIGH (>=25), VERY HIGH, EXCLUDED / MANUAL REVIEW. \
grid_source "estimated" means a rough approximation, not a map. practicality_completeness is the share of the five dimensions available. \
pareto_field / pareto_facility = not beaten by any other match on both similarity and that practicality score.
- Constraints are flags: ok, warning, manual_review, excluded, missing. community_rights is always manual_review because no land-rights dataset was checked - \
it never means "clear". hard_excluded = true means an excluded flag; exclusion_reasons explains why.
- Practicality is coarse (1 km data), a screening aid, not a cost estimate.
"""


class ChatUnavailable(Exception):
    pass


class ChatMessage(Model):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequest(Model):
    moon_site_id: str = Field(examples=["moon_apollo_15"])
    selected_twin_id: str | None = Field(
        default=None, description="patch_id dopasowania, ktÃ³re uÅ¼ytkownik ma teraz otwarte ('ten', 'this one')."
    )
    messages: list[ChatMessage] = Field(min_length=1, description="Historia rozmowy; ostatnia wiadomoÅ›Ä‡ to pytanie (role=user).")


def _round(value, digits: int = 2):
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, dict):
        return {k: _round(v, digits) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v, digits) for v in value]
    return value


@lru_cache(maxsize=1)
def _glossary_features() -> list[dict]:
    return [f.model_dump(mode="json") for f in service.meta().features]


@lru_cache(maxsize=32)
def _context(site_id: str) -> tuple[str, dict[str, str]]:
    """(tekst kontekstu, {patch_id: etykieta '#1 Nazwa'}) dla miejsca KsiÄ™Å¼yca."""
    response = service.analogs(AnalogsRequest(moon=MoonQuery(site_id=site_id), **CONTEXT_REQUEST))
    moon = response.moon.model_dump(mode="json", exclude_none=True)
    moon.pop("z_scores", None)
    matches, labels = [], {}
    for item in response.results:
        data = item.model_dump(mode="json", exclude_none=True)
        for key in ("z_scores", "stability", "composition_confidence", "composition_source"):
            data.pop(key, None)
        (data.get("practicality") or {}).pop("practicality_confidence", None)
        labels[item.patch_id] = f"#{item.rank} {item.region_name}"
        matches.append(data)
    payload = {
        "moon_site": moon,
        "earth_matches_ranked": matches,
        "feature_glossary": _glossary_features(),
        "known_limitations": service.LIMITATIONS,
    }
    return json.dumps(_round(payload), ensure_ascii=False, separators=(",", ":")), labels


def _system_instruction(site_id: str, selected_twin_id: str | None) -> str:
    data, labels = _context(site_id)
    parts = [SYSTEM_PROMPT, "DATA (JSON)", data]
    if selected_twin_id in labels:
        parts.append(f"The user currently has match {labels[selected_twin_id]} (patch_id {selected_twin_id}) open; 'this one' means that match.")
    return "\n".join(parts)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        return "The AI service is rate limited right now. Wait a few seconds and try again."
    if "API key" in text or "API_KEY" in text or "401" in text or "403" in text:
        return "The AI service rejected the API key. Check GOOGLE_API_KEY in .env."
    return "The AI service did not answer. Try again."


def _thinking(model: str):
    """MaÅ‚o 'myÅ›lenia', Å¼eby pierwsze sÅ‚owa pojawiaÅ‚y siÄ™ szybko; nazwa parametru zaleÅ¼y od generacji modelu."""
    from google.genai import types

    if model.startswith("gemini-2.5"):
        return types.ThinkingConfig(thinking_budget=512)
    if model.startswith("gemini-3"):
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
    return None


async def _stream(model: str, system: str, messages: list[ChatMessage]) -> AsyncIterator[str]:
    from google import genai
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.3,
        max_output_tokens=1024,
        thinking_config=_thinking(model),
    )
    contents = [
        types.Content(role="user" if m.role == "user" else "model", parts=[types.Part.from_text(text=m.content)])
        for m in messages
    ]
    try:
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"], http_options=types.HttpOptions(timeout=45000))
        stream = await client.aio.models.generate_content_stream(model=model, contents=contents, config=config)
        async for chunk in stream:
            if chunk.text:
                yield _sse("delta", {"text": chunk.text})
        yield _sse("done", {})
    except Exception as exc:  # bÅ‚Ä…d po rozpoczÄ™ciu strumienia idzie jako zdarzenie, nie status HTTP
        logging.getLogger("uvicorn.error").warning("chat stream failed: %s: %s", type(exc).__name__, str(exc)[:300])
        yield _sse("error", {"message": _friendly_error(exc)})


router = APIRouter()


@router.post(
    "/chat",
    tags=["chat"],
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "SSE: `delta` {text}, potem `done` albo `error` {message}."},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def post_chat(req: ChatRequest):
    """OdpowiedÅº asystenta (strumieÅ„ SSE) na pytanie o miejsce KsiÄ™Å¼yca i jego analogi."""
    if not os.environ.get("GOOGLE_API_KEY"):
        body = ErrorResponse(code="CHAT_UNAVAILABLE", message="The assistant is not configured: set GOOGLE_API_KEY in .env.")
        return JSONResponse(status_code=503, content=body.model_dump(mode="json"))
    if req.messages[-1].role != "user":
        body = ErrorResponse(code="INVALID_REQUEST", message="The last message must be from the user.")
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))
    system = await run_in_threadpool(_system_instruction, req.moon_site_id, req.selected_twin_id)
    model = os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
    return StreamingResponse(
        _stream(model, system, req.messages[-MAX_HISTORY:]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
