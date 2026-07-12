import sys, os, re
import fitz  # PyMuPDF
from multiprocessing import Pool

math_tokens = ["α","β","γ","δ","θ","λ","μ","π","ρ","σ","φ","ω","Δ","Σ","√","×10","²","³","≈","≤","≥","±","∝"]
eq_pat = re.compile(r"([A-Za-z]\s*=\s*[A-Za-z0-9\s\.\+\-\*/\(\)]+)|(E\s*=|F\s*=|v\s*=|a\s*=|P\s*=|V\s*=|I\s*=|R\s*=)")
practical_kw = ["apparatus","method","variable","risk","safety","hazard","hypothesis","investigation","procedure","results table","observation"]
exam_kw = ["total marks","[total","marks)","mark scheme","question paper"]
table_kw = ["table","tabulate","results table"]
diagram_kw = ["diagram","circuit","ray diagram","free-body","free body","apparatus","figure","graph","plot"]
worked_kw = ["worked example","solution:","worked solution","step 1","step 2"]

def analyze(path):
    try:
        doc = fitz.open(path)
    except Exception:
        return None
    pages = doc.page_count
    text_parts = []
    images = 0
    for p in doc:
        text_parts.append(p.get_text())
        images += len(p.get_images(full=True))
    text = "\n".join(text_parts)
    low = text.lower()
    has_eq = any(tok in text for tok in math_tokens) or bool(eq_pat.search(text))
    has_table = any(k in low for k in table_kw)
    has_diagram = any(k in low for k in diagram_kw)
    has_graph = ("graph" in low) or ("plot" in low) or ("axis" in low) or ("y-axis" in low) or ("x-axis" in low)
    has_image = images > 5
    has_practical = sum(k in low for k in practical_kw) >= 2
    has_exam = any(k in low for k in exam_kw) or bool(re.search(r"\b\d+\s*marks?\b", low))
    base = os.path.basename(path).lower()
    has_ms = ("mark" in base) or ("ms" in base) or ("scheme" in base) or ("answers" in base) or ("ans" in base) or ("mark scheme" in low) or ("marking" in low)
    has_worked = any(k in low for k in worked_kw)
    assets = {
        "graph": has_graph, "table": has_table, "equation": has_eq,
        "diagram": has_diagram, "practical": has_practical, "image": has_image,
        "exam": has_exam, "markscheme": has_ms, "worked": has_worked,
    }
    score = sum(2 for v in assets.values() if v)
    doc.close()
    det = ",".join(k for k,v in assets.items() if v)
    return (score, path, pages, images, det)

if __name__ == "__main__":
    with open(sys.argv[1]) as fh:
        pdfs = [l.strip() for l in fh if l.strip()]
    with Pool(8) as pool:
        for r in pool.imap_unordered(analyze, pdfs, chunksize=16):
            if r is None:
                continue
            score, path, pages, images, det = r
            print(f"{score}\t{path}\t{pages}\t{images}\t{det}", flush=True)
