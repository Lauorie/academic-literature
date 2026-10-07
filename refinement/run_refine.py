#!/usr/bin/env python3
"""Run SkillRefiner on the academic-literature corpus (skillrefine/LABELS.md).

LLM: openai/gpt-5.4-mini via the PaperBypass gateway; embeddings: text-embedding-3-small via OpenRouter.
Credentials come from /home/juli/citation/DAS/.env (PAPERBYPASS_AUTH_TOKEN, OP_TOKEN); nothing is written to disk.
Usage (from the SkillRefiner checkout): uv run python <this> <corpus dir> <output dir>
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import litellm
from dotenv import dotenv_values

from skill_refiner.pipeline import RefineConfig, refine

MODEL = "openai/openai/gpt-5.4-mini"  # litellm strips one prefix; the gateway expects openai/gpt-5.4-mini
SEED = Path(__file__).resolve().parent / "seed_SKILL.md"


def main() -> int:
    corpus, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    env = dotenv_values("/home/juli/citation/DAS/.env")
    os.environ["LLM_API_KEY"] = env["PAPERBYPASS_AUTH_TOKEN"]
    os.environ["SKILL_REFINER_BASE_URL_EVAL_PROXY"] = "https://aigateway.paperbypass.com/api/v1"
    os.environ["EMBEDDING_API_KEY"] = env["OP_TOKEN"]
    # Without this entry litellm knows no context window for MODEL and the summarizer falls back to 16k tokens.
    litellm.register_model({MODEL: {"max_input_tokens": 272000, "max_output_tokens": 128000,
                                    "input_cost_per_token": 0.75e-6, "output_cost_per_token": 4.5e-6,
                                    "litellm_provider": "openai", "mode": "chat"}})
    config = RefineConfig(skill_file=SEED, skill_name="academic-literature",
                          raw_jsonl=corpus / "traces.jsonl", binary_rewards=corpus / "binary_rewards.json",
                          output_dir=out, model=MODEL,
                          embedding_model=env.get("OP_MODEL", "openai/text-embedding-3-small"),
                          embedding_base_url="https://openrouter.ai/api/v1")
    asyncio.run(refine(config))
    print(out / "combined" / "proposed_skill.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
