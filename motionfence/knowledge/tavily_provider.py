"""Tavily search provider for operational documentation and engineering manual retrieval."""

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any, Callable, Dict, List, Optional

from motionfence.knowledge.models import KnowledgeEvidence, TrustStatus
from motionfence.knowledge.provider import TavilyProviderError
from motionfence.config.settings import settings

logger = logging.getLogger("motionfence.knowledge.tavily")


class TavilyKnowledgeProvider:
    """Retrieves external engineering knowledge and plant manuals via the Tavily Search API.
    
    STATUS: IMPLEMENTED — NOT LIVE VERIFIED (Pending live credentials)
    SECURITY INVARIANT:
    All retrieved content is marked UNVERIFIED_EXTERNAL.
    External text is treated as untrusted evidence and can NEVER directly actuate machinery.
    """

    provider_name: str = "tavily"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        max_results: Optional[int] = None,
        http_requester: Optional[Callable[[str, Dict[str, Any], float], Dict[str, Any]]] = None,
        transport: Optional[Callable[[str, Dict[str, Any], float], Dict[str, Any]]] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.tavily.api_key
        self.timeout = timeout if timeout is not None else settings.tavily.timeout_seconds
        self.max_results = max_results if max_results is not None else settings.tavily.max_results
        self._http_requester = transport or http_requester or self._default_http_post

    def retrieve(self, query: str) -> List[KnowledgeEvidence]:
        """Execute Tavily search query and return normalized KnowledgeEvidence items."""
        if not self.api_key or self.api_key == "placeholder_key_offline":
            raise TavilyProviderError("TAVILY_API_KEY environment variable is not configured.")

        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": self.max_results,
            "include_answer": False,
        }

        try:
            data = self._http_requester("https://api.tavily.com/search", payload, self.timeout)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise TavilyProviderError(f"Tavily authentication error (HTTP {e.code}): Invalid API key.") from e
            raise TavilyProviderError(f"Tavily API HTTP error {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise TavilyProviderError(f"Tavily network connection error: {e.reason}") from e
        except TimeoutError as e:
            raise TavilyProviderError(f"Tavily request timed out after {self.timeout}s.") from e
        except Exception as e:
            raise TavilyProviderError(f"Unexpected Tavily retrieval error: {e}") from e

        if not isinstance(data, dict):
            raise TavilyProviderError("Malformed Tavily response: root must be a JSON object.")

        raw_results = data.get("results", [])
        if not isinstance(raw_results, list):
            raise TavilyProviderError("Malformed Tavily response: 'results' must be a list.")

        evidence_list: List[KnowledgeEvidence] = []
        now = time.time()

        for idx, res in enumerate(raw_results):
            if not isinstance(res, dict):
                continue

            title = res.get("title", f"Tavily Result {idx+1}")
            url = res.get("url", "https://tavily.com")
            content = res.get("content", "").strip()
            score = float(res.get("score", 0.85)) if res.get("score") is not None else 0.85
            score = max(0.0, min(1.0, score))

            if not content:
                continue

            evidence_list.append(
                KnowledgeEvidence(
                    id=f"kb_tavily_{idx+1}_{int(now)}",
                    query=query,
                    title=title,
                    source_url=url,
                    content=content,
                    retrieved_at=now,
                    source_metadata={"tavily_score": score, "raw": res},
                    provenance=f"tavily:search:{url}",
                    confidence=score,
                    trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
                )
            )

        return evidence_list

    @classmethod
    def _default_http_post(cls, url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        """Perform standard library HTTP POST request."""
        try:
            import truststore
            truststore.inject_into_ssl()
        except Exception:
            pass

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "MotionFence/0.1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8")
            return json.loads(raw_body)
