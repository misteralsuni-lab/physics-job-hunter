#!/usr/bin/env python3
"""
Temperature A/B/C test for cover-letter generator's OpenCode Zen call.

Tests three temperature settings against three realistic job postings.

Settings:
  A: 0.3  (current, reasoning-mode-optimised)
  B: 0.8  (sibling-provider temperature, prose-warm)
  C: dynamic (0.7 fall-through / 0.3 reasoning-mode)

Runs each combination and records:
  - latency
  - finish_reason
  - content length
  - reasoning length
  - token counts
  - full cover letter text

Saves raw output to /tmp/cover_letter_temp_ab/ for offline review.
"""

import os, sys, json, time, copy, hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import httpx

# ---------------------------------------------------------------------------
# Setup --------------------------------------------------------------------
# ---------------------------------------------------------------------------

sys.path.insert(0, "/mnt/d/physics-job-hunter")

# Fresh import
mods = [k for k in list(sys.modules) if k.startswith("src.")]
for m in mods:
    del sys.modules[m]

from src.config import settings
from src.generators.cover_letter import CoverLetterGenerator

OUT_DIR = Path("/tmp/cover_letter_temp_ab")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Test data ----------------------------------------------------------------
# ---------------------------------------------------------------------------

JOBS = [
    {
        "id": "job_1",
        "title": "Lead Teacher of Physics — Secondary",
        "school": "Harrow International School",
        "country": "UAE",
        "curriculum": ["IGCSE", "A-Level"],
        "subject": ["Physics"],
    },
    {
        "id": "job_2",
        "title": "Secondary Physics Teacher (KS4/KS5)",
        "school": "GEMS Wellington International School",
        "country": "UAE",
        "curriculum": ["IGCSE"],
        "subject": ["Physics"],
    },
    {
        "id": "job_3",
        "title": "Physics & Maths Teacher (covers Head of Dept role)",
        "school": "Doha College",
        "country": "Qatar",
        "curriculum": ["A-Level", "IB"],
        "subject": ["Physics", "Maths"],
    },
]

PROFILE = {
    "target_subjects": ["Physics", "Science"],
    "target_curricula": ["IGCSE", "A-Level"],
    "target_countries": ["UAE", "Qatar", "Saudi Arabia", "Singapore", "China", "Thailand"],
    "gender": "Male",
    "visa_sponsorship_required": True,
    "housing_allowance_preferred": True,
    "leadership_opportunities": True,
    "leadership_role_preference": ["Head of Physics", "Subject Lead", "STEM Coordinator", "STEM Lead"],
    "cv_summary": (
        "STEM Lead & Head of Physics candidate with three years' post-qualifying classroom "
        "experience delivering Pearson Edexcel IGCSE and A-Level Physics at Vision International "
        "School (Registered British Examination Centre), Tripoli. PGCEi candidate at Liverpool "
        "John Moores University (LJMU, UK) due 2026. B.Sc. Mechanical Engineering (University of "
        "Tripoli, 2020). Personally authored the school's full KS4/KS5 Edexcel Physics schemes "
        "of work, required practicals, and lab-safety procedures (CLEAPSS-aligned), and founded "
        "the engineering-linked STEM enrichment programme (industry visits, applied modelling). "
        "Concurrent appointment through 2024 at Kids Academy School (Cognia Accredited) for "
        "IGCSE/A-Level Physics intervention; prior KS3 Science and Chemistry at Ladybird "
        "International School (2022-2023). Engineering background (Alsahl Group, 2021-2022 - "
        "Technical Training & Diagnostics Specialist; Engineering Intern, Accuracy for "
        "Maintenance, 2020-2021) underpins uniquely credible delivery of Mechanics, "
        "Thermodynamics, Fluid Dynamics, and Electronics at GCSE and A-Level. Strong advocate "
        "of inclusive pedagogy, formative assessment (AfL), safeguarding, and current PGCEi "
        "continuing professional development."
    ),
}

TEMPERATURES = {
    "A_0.3": {"temperature": 0.3, "label": "A_0.3"},
    "B_0.8": {"temperature": 0.8, "label": "B_0.8"},
    "C_dynamic": {"temperature": "dynamic", "label": "C_dynamic"},
}

# ---------------------------------------------------------------------------
# Prompt builder -----------------------------------------------------------
# ---------------------------------------------------------------------------

def build_prompt(job: Dict[str, Any]) -> str:
    """Build the exact cover-letter prompt used by the production generator."""
    curriculum_str = ", ".join(job.get("curriculum", []))
    return (
        "You are an expert cover-letter writer. Write a formal 3-paragraph cover letter "
        "for the following job, signed by Mahmoud Alsini:\n\n"
        f"Job:\nTitle: {job['title']}\nSchool: {job['school']}\nCountry: {job['country']}\n"
        f"Curriculum: {curriculum_str}\n\n"
        "Profile (recruiter's view):\n"
        "Mahmoud is a STREAM Lead who teaches Pearson Edexcel IGCSE and A-Level Physics "
        "at Vision International School. Three years classroom experience. PGCEi candidate "
        "at Liverpool John Moores University. B.Sc. Mechanical Engineering (University of "
        "Tripoli, 2020).\n\n"
        "Write the letter now."
    )

# ---------------------------------------------------------------------------
# API call wrapper ---------------------------------------------------------
# ---------------------------------------------------------------------------

def call_opencode_zen(prompt: str, temperature: float, max_tokens: int = 4096, timeout: int = 60) -> Dict:
    """Call OpenCode Zen /chat/completions with given temperature."""
    t0 = time.time()
    try:
        resp = httpx.post(
            "https://opencode.ai/zen/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.opencode_zen_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-v4-flash-free",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": 4096,
            },
            timeout=60,
        )
        elapsed = time.time() - t0
        body = resp.json() if resp.status_code == 200 else {"error": resp.text}
        msg = body.get("choices", [{}])[0].get("message", {}) if isinstance(body, dict) else {}
        return {
            "status": resp.status_code,
            "elapsed": round(time.time() - t0, 2),
            "finish_reason": body.get("choices", [{}])[0].get("finish_reason") if isinstance(body, dict) else None,
            "content": msg.get("content") or "",
            "reasoning": msg.get("reasoning_content") or "",
            "usage": body.get("usage", {}) if isinstance(body, dict) else {},
            "raw": body,
        }
    except Exception as e:
        return {
            "status": 0,
            "elapsed": round(time.time() - t0, 2),
            "error": str(e),
            "content": "",
            "reasoning": "",
        }

# ---------------------------------------------------------------------------
# Test runner --------------------------------------------------------------
# ---------------------------------------------------------------------------

def run_all():
    """Execute the full A/B/C sweep across 3 jobs × 3 temps = 9 runs."""
    results = []
    
    print("=" * 70)
    print("COVER LETTER TEMPERATURE A/B/C TEST")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)
    
    for job in JOBS:
        prompt = build_prompt(job)
        
        for temp_key, temp_cfg in TEMPERATURES.items():
            temps_to_try = []
            if temp_cfg["temperature"] == "dynamic":
                # C_dynamic: first call at 0.7, if empty content then retry at 0.3
                temps_to_try = [(0.7, "C_dynamic_0.7"), (0.3, "C_dynamic_0.3")]
            else:
                temps_to_try = [(temp_cfg["temperature"], temp_cfg["label"])]
            
            for temp_val, label in temps_to_try:
                print(f"\n--- Job: {job['id']} | Temp: {label} ({temp_val}) ---")
                
                res = call_opencode_zen(build_prompt(job), temp_val)
                
                # For dynamic: if first attempt returns empty content, retry at 0.3
                if temp_cfg["temperature"] == "dynamic" and label == "C_dynamic_0.7":
                    content_len = len(res.get("content", ""))
                    if content_len == 0:
                        print(f"   ⚠ Dynamic 0.7 returned empty — falling back to 0.3")
                        res = call_opencode_zen(build_prompt(job), 0.3)
                        label = "C_dynamic_fallback_0.3"
                
                result = {
                    "job_id": job["id"],
                    "job_title": JOBS[JOBS.index(job)]["title"] if job in JOBS else job.get("title", ""),
                    "temperature_label": label,
                    "temperature_value": res.get("temperature") if "temperature" in res else (0.3 if "fallback" in label else 0.8),
                    "status": res.get("status"),
                    "elapsed": res.get("elapsed"),
                    "finish_reason": res.get("finish_reason"),
                    "content_length": len(res.get("content", "")),
                    "reasoning_length": len(res.get("reasoning", "")),
                    "content": res.get("content", ""),
                    "reasoning": res.get("reasoning", ""),
                    "usage": res.get("usage", {}),
                    "raw_usage": res.get("usage", {}),
                    "error": res.get("error"),
                }
                
                results.append(result)
                
                # Quick summary
                status = res.get("status", "err")
                cl = len(res.get("content", ""))
                rl = len(res.get("reasoning", ""))
                finish = res.get("finish_reason", "?")
                elapsed = res.get("elapsed", "?")
                print(f"   status={status} elapsed={elapsed}s finish={finish} content_len={cl} reasoning_len={len(res.get('reasoning',''))}")
                
                # Small delay to be polite
                time.sleep(1.5)
    
    return results


# ---------------------------------------------------------------------------
# Evaluation ---------------------------------------------------------------
# ---------------------------------------------------------------------------

def evaluate(results: List[Dict]) -> List[Dict]:
    """Score each cover letter on 5 qualitative dimensions (1-5)."""
    scored = []
    for r in results:
        content = r.get("content", "")
        reasoning = r.get("reasoning", "")
        
        # Proxy metrics
        content_len = len(r.get("content", ""))
        reasoning_len = len(r.get("reasoning", ""))
        has_proper_greeting = 1 if content.strip().startswith("Dear") else 0
        has_signoff = 1 if "faithfully" in content.lower() or "sincerely" in content.lower() else 0
        mentions_edexcel = 1 if "edexcel" in content.lower() else 0
        mentions_igcse = 1 if "igcse" in content.lower() else 0
        mentions_a_level = 1 if "a-level" in content.lower() or "a level" in content.lower() else 0
        mentions_stem = 1 if "stem" in content.lower() else 0
        mentions_engineering = 1 if "engineering" in content.lower() else 0
        mentions_pgcei = 1 if "pgcei" in content.lower() else 0
        
        # Composite heuristic score (max ~10)
        score = (
            min(len(r.get("content", "")) // 200, 5) +  # length up to 5
            has_proper_greeting +
            has_signoff +
            mentions_edexcel +
            mentions_igcse +
            mentions_a_level +
            mentions_stem +
            mentions_engineering +
            mentions_pgcei
        )
        
        scored.append({
            **r,
            "heuristic_score": min(score, 25),
            "content_preview": r.get("content", "")[:300],
        })
    
    return scored


# ---------------------------------------------------------------------------
# Main ---------------------------------------------------------------------
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Starting temperature A/B/C test...")
    all_results = run_all()
    
    # Evaluate
    scored = list(evaluate(all_results))
    
    # Save raw
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = OUT_DIR / f"temperature_ab_raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(raw_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nRaw results saved: {raw_path}")
    
    # Save scored summary
    scored_path = OUT_DIR / f"temperature_ab_scored_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(scored_path, "w") as f:
        json.dump(list(scored), f, indent=2, default=str)
    print(f"Scored results saved: {scored_path}")
    
    # Print summary table
    print("\n" + "=" * 70)
    print("SUMMARY TABLE")
    print("=" * 70)
    for r in scored:
        print(f"{r['job_id']} | {r['temperature_label']:15s} | "
              f"len={r['content_length']:4d} | "
              f"reasoning={r['reasoning_length']:4d} | "
              f"finish={r['finish_reason'] or '?':8s} | "
              f"score={r['heuristic_score']} | "
              f"{r['content_preview'][:80]}...")