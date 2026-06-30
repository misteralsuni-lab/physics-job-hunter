#!/usr/bin/env python3
"""
Generate redesign v2: ATS-optimised CV for Mahmoud Alsini
Aligned with reviewer recommendations (evidence-based profile, measurable impact
wording where truthful, expanded PD focus, compact refs, EdTech, KS3-5 keywords).
"""

from weasyprint import HTML
import os

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="UTF-8">
<style>
  @page {
    size: A4;
    margin: 1.1cm 1.4cm 1.1cm 1.4cm;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: 'Segoe UI', 'Calibri', 'Helvetica Neue', Arial, sans-serif;
    font-size: 8.7pt;
    line-height: 1.38;
    color: #1a1a1a;
    background: #fff;
  }

  /* ── HEADER ── */
  .header {
    text-align: center;
    padding-bottom: 4px;
    border-bottom: 2px solid #1a3a5c;
    margin-bottom: 6px;
  }
  .header h1 {
    font-size: 17pt;
    font-weight: 700;
    color: #1a3a5c;
    letter-spacing: 0.5pt;
    margin-bottom: 1px;
  }
  .header .headline {
    font-size: 9pt;
    color: #1a3a5c;
    font-weight: 600;
    margin-bottom: 2px;
  }
  .header .contact {
    font-size: 8pt;
    color: #555;
  }
  .header .contact span { display: inline-block; margin: 0 4px; }
  .header .contact .sep { color: #bbb; }

  /* ── SECTION HEADINGS ── */
  .section-title {
    font-size: 9.5pt;
    font-weight: 700;
    color: #1a3a5c;
    text-transform: uppercase;
    letter-spacing: 0.7pt;
    border-bottom: 0.8px solid #ccc;
    padding-bottom: 1px;
    margin-top: 7px;
    margin-bottom: 3px;
  }
  .section-title:first-of-type { margin-top: 0; }

  /* ── PROFILE ── */
  .profile-text {
    font-size: 8.4pt;
    line-height: 1.38;
    text-align: justify;
    margin-bottom: 1px;
  }

  /* ── COMPETENCIES GRID ── */
  .competencies {
    column-count: 3;
    column-gap: 10px;
    column-rule: none;
    margin-bottom: 2px;
    font-size: 8pt;
  }
  .competencies li {
    padding: 0 0 0 10px;
    position: relative;
    break-inside: avoid;
    list-style: none;
  }
  .competencies ul { padding: 0; margin: 0; }
  .competencies li::before {
    content: "\\25CF";
    position: absolute;
    left: 0;
    color: #1a3a5c;
    font-size: 5pt;
    top: 1px;
  }

  /* ── Education ── */
  .edu-entry { margin-bottom: 3px; }
  .edu-entry .edu-title { font-weight: 600; font-size: 8.5pt; }
  .edu-entry .edu-meta  { font-size: 8pt; color: #555; }
  .edu-entry .edu-note  { font-size: 7.8pt; color: #666; font-style: italic; }

  /* ── JOB ENTRIES ── */
  .job { margin-bottom: 5px; page-break-inside: avoid; }
  .job-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  .job-title  { font-weight: 700; font-size: 9pt; color: #1a3a5c; }
  .job-org    { font-weight: 600; font-size: 8.5pt; }
  .job-dates  { font-size: 8pt; color: #666; white-space: nowrap; }
  .job-location { font-size: 7.8pt; color: #777; margin-bottom: 1px; }
  .job ul {
    list-style: none;
    padding: 0;
    margin: 1px 0 0 0;
  }
  .job ul li {
    font-size: 8.3pt;
    line-height: 1.36;
    padding: 0 0 0 12px;
    position: relative;
  }
  .job ul li::before {
    content: "\\2022";
    position: absolute;
    left: 1px;
    color: #1a3a5c;
    font-weight: bold;
  }

  .concurrent-note {
    font-size: 7.5pt;
    color: #666;
    font-style: italic;
    margin-top: -2px;
    margin-bottom: 2px;
  }

  /* ── PD block ── */
  .pd-grid {
    column-count: 2;
    column-gap: 12px;
    font-size: 8pt;
  }
  .pd-grid li {
    list-style: none;
    padding: 0 0 0 11px;
    position: relative;
    break-inside: avoid;
  }
  .pd-grid li::before {
    content: "\\25CF";
    position: absolute;
    left: 0;
    color: #1a3a5c;
    font-size: 5pt;
    top: 2px;
  }
  .pd-grid ul { padding: 0; margin: 0; }

  /* ── REFEREES ── */
  .referee-line {
    font-size: 8pt;
    line-height: 1.32;
    margin-bottom: 2px;
  }

  .body-p { font-size: 8.3pt; line-height: 1.36; margin-bottom: 2px; }
  .no-break { page-break-inside: avoid; }
</style>
</head>
<body>

<!-- ═══════════════ HEADER ═══════════════ -->
<div class="header">
  <h1>MAHMOUD ALSINI</h1>
  <div class="headline">Secondary Physics Teacher &nbsp;|&nbsp; Pearson Edexcel IGCSE & A-Level &nbsp;|&nbsp; Mechanical Engineer &nbsp;|&nbsp; PGCEi Candidate</div>
  <div class="contact">
    <span>Tripoli, Libya</span>
    <span class="sep">|</span>
    <span>+218 (0)91 909 9293</span>
    <span class="sep">|</span>
    <span>alsunimahmoud@gmail.com</span>
    <span class="sep">|</span>
    <span>linkedin.com/in/eng-mahmoud-alsini</span>
  </div>
</div>

<!-- ═══════════════ PROFILE ═══════════════ -->
<div class="section-title">Professional Profile</div>
<p class="profile-text">
Secondary Physics educator with three years of post-qualifying classroom experience and a 
B.Sc. in Mechanical Engineering, currently completing the PGCEi (Postgraduate Certificate in 
Education – International) at Liverpool John Moores University (LJMU), UK. Delivers the full 
<strong>Pearson Edexcel IGCSE</strong> and <strong>A-Level Physics</strong> specification at a 
registered British examination centre in Tripoli, alongside KS3 Science at the same campus, with 
sustained responsibility for curriculum planning, formative and summative <strong>assessment</strong>, 
and inclusive classroom practice across KS4 and KS5 cohorts. Teaching philosophy is rooted in 
<strong>inquiry-based</strong>, student-centred learning where students derive physical principles 
from observation and experimentation, supported by rigorous <strong>differentiation</strong> and 
<strong>Assessment for Learning</strong>. Strong advocate of <strong>inclusive pedagogy</strong>, 
<strong>safeguarding</strong>, and <strong>behaviour management</strong>; committed to ongoing 
professional growth and evidence-based practice through PGCEi studies at an internationally 
respected UK provider.
</p>

<!-- ═══════════════ CORE COMPETENCIES ═══════════════ -->
<div class="section-title">Core Competencies</div>
<div class="competencies">
  <ul>
    <li>Pearson Edexcel IGCSE Physics</li>
    <li>Pearson Edexcel A-Level Physics</li>
    <li>KS3 Science & KS4/KS5 Physics</li>
    <li>Curriculum Planning & Mapping</li>
    <li>Assessment for Learning (AfL)</li>
    <li>Summative Assessment & Examination</li>
  </ul>
  <ul>
    <li>Differentiation & Scaffolding</li>
    <li>Inclusive Education & SEN Awareness</li>
    <li>Safeguarding & Child Protection</li>
    <li>Behaviour Management</li>
    <li>Laboratory Safety & Practical Physics</li>
    <li>STEM Education & Enrichment</li>
  </ul>
  <ul>
    <li>Inquiry-Based Learning (IBL)</li>
    <li>Microsoft Teams (online instruction)</li>
    <li>Google Workspace for Education</li>
    <li>Microsoft Office Suite</li>
    <li>Interactive Simulations & Virtual Labs</li>
    <li>Educational Technology Integration</li>
  </ul>
</div>

<!-- ═══════════════ TEACHING EXPERIENCE ═══════════════ -->
<div class="section-title">Teaching Experience</div>

<!-- Job 1 -->
<div class="job no-break">
  <div class="job-header">
    <div>
      <span class="job-title">Physics Teacher (IGCSE & A-Level) &mdash; KS4 / KS5</span>
      <span class="job-org"> &mdash; Vision International School (Registered Pearson Edexcel Examination Centre), Tripoli, Libya</span>
    </div>
    <div class="job-dates">Sept 2023 &ndash; Present</div>
  </div>
  <ul>
    <li>Designed and delivered the full Pearson Edexcel IGCSE and A-Level Physics specification across KS4 and KS5, supporting student preparation for external examinations.</li>
    <li>Wrote schemes of work and lesson sequences aligned to the Edexcel specification, covering Mechanics, Waves, Electricity & Magnetism, Thermal Physics, Particle Physics, and Practical Skills.</li>
    <li>Planned and led industry-linked STEM visits and engineering field trips that connected abstract Physics theory with industrial applications and engineering career pathways.</li>
    <li>Embedded mathematical modelling, worked problems, and engineering case studies into lessons to support students aiming for degrees in Engineering, Architecture, and the Physical Sciences.</li>
    <li>Applied formative Assessment for Learning &mdash; hinge questions, exit tickets, and targeted feedback &mdash; to monitor progress and adapt teaching to mixed-attainment learners.</li>
    <li>Maintained safeguarding, behaviour management, and laboratory safety standards in line with school policy during every practical session.</li>
  </ul>
</div>

<!-- Job 2 -->
<div class="job no-break">
  <div class="job-header">
    <div>
      <span class="job-title">Physics Teacher (IGCSE & A-Level) &mdash; KS4 / KS5</span>
      <span class="job-org"> &mdash; Kids Academy School (Cognia Accredited), Tripoli, Libya</span>
    </div>
    <div class="job-dates">2024</div>
  </div>
  <div class="concurrent-note">Concurrent appointment alongside Vision International School</div>
  <ul>
    <li>Delivered targeted small-group Physics instruction and intensive revision programmes for IGCSE and A-Level candidates preparing for terminal examinations.</li>
    <li>Diagnosed individual learning gaps in topics such as electromagnetic induction and circular motion, then designed bespoke intervention plans to improve exam readiness.</li>
    <li>Integrated required practicals and data-analysis activities to strengthen students&rsquo; experimental-methods skills under the Pearson Edexcel specification.</li>
  </ul>
</div>

<!-- Job 3 -->
<div class="job no-break">
  <div class="job-header">
    <div>
      <span class="job-title">Science Teacher (KS3 Science & Secondary Chemistry)</span>
      <span class="job-org"> &mdash; Ladybird International School, Tripoli, Libya</span>
    </div>
    <div class="job-dates">2022 &ndash; 2023</div>
  </div>
  <ul>
    <li>Taught secondary Science (including KS3 Science and Chemistry to IGCSE-adjacent standards), preparing diverse cohorts for progression to upper-secondary international curricula.</li>
    <li>Used data from progress checks and mock examinations to set individual academic targets and adjust instruction for mixed-prior-attainment groups.</li>
    <li>Built strong foundations in atomic structure, bonding, and reaction kinetics to ease the transition into IGCSE Science pathways.</li>
    <li>Applied inclusive teaching practices and positive behaviour management to support learners with varied prior attainment and English-language proficiency.</li>
  </ul>
</div>

<!-- ═══════════════ ACHIEVEMENTS & ENRICHMENT ═══════════════ -->
<div class="section-title">Curriculum & Enrichment Highlights</div>
<ul class="pd-grid">
  <li>Wrote full Pearson Edexcel IGCSE and A-Level Physics schemes of work aligned to the current specification.</li>
  <li>Designed school-based required practicals and risk assessments for KS4 and KS5 Physics.</li>
  <li>Organised industry-linked STEM visits to connect classroom Physics with engineering careers.</li>
  <li>Developed revision programmes for IGCSE and A-Level terminal-examination cohorts.</li>
  <li>Built formative-assessment resources (hinge questions, exit tickets, topic test banks).</li>
  <li>Contributed to departmental moderation and examination-standardisation conversations.</li>
</ul>

<!-- ═══════════════ EDUCATION & QUALIFICATIONS ═══════════════ -->
<div class="section-title">Education & Qualifications</div>

<div class="edu-entry no-break">
  <div class="edu-title">PGCEi &mdash; Postgraduate Certificate in Education (International) <span class="edu-meta">&nbsp;&mdash;&nbsp; In Progress</span></div>
  <div class="edu-meta">Liverpool John Moores University (LJMU), UK &middot; Module 7532-PCEI &middot; 2025&ndash;2026</div>
  <div class="edu-note">UK-standard initial teacher training for international contexts: planning, assessment, behaviour management, inclusion, safeguarding.</div>
</div>

<div class="edu-entry no-break">
  <div class="edu-title">B.Sc. Mechanical Engineering (Engineering Science) <span class="edu-meta">&nbsp;&mdash;&nbsp; Graduated 2020</span></div>
  <div class="edu-meta">University of Tripoli, Faculty of Engineering, Libya</div>
  <div class="edu-note">Core modules anchored in Mechanics, Thermodynamics, Fluid Dynamics, and Electricity & Magnetism &mdash; the foundation for confident KS4/KS5 Physics delivery.</div>
</div>

<!-- ═══════════════ ENGINEERING & TECHNICAL EXPERIENCE ═══════════════ -->
<div class="section-title">Engineering & Technical Experience</div>

<div class="job no-break">
  <div class="job-header">
    <div>
      <span class="job-title">Technical Training & Diagnostics Specialist</span>
      <span class="job-org"> &mdash; Alsahl Group, Tripoli, Libya</span>
    </div>
    <div class="job-dates">2021 &ndash; 2022</div>
  </div>
  <ul>
    <li>Designed and delivered training programmes on the integration, diagnostics, and maintenance of heavy machinery (generators and forklifts) for professional engineering teams.</li>
    <li>Conducted technical research that improved diagnostic workflows and the operational lifecycle of machinery across the organisation.</li>
    <li>Translated complex mechanical-system principles into clear, practical instruction for technicians &mdash; directly transferable to scaffolding difficult Physics concepts for diverse learners.</li>
  </ul>
</div>

<div class="job no-break">
  <div class="job-header">
    <div>
      <span class="job-title">Engineering Intern</span>
      <span class="job-org"> &mdash; Accuracy for Maintenance, Tripoli, Libya</span>
    </div>
    <div class="job-dates">2020 &ndash; 2021</div>
  </div>
  <ul>
    <li>Supported troubleshooting, diagnostic analysis, and routine maintenance of industrial mechanical systems, with practical exposure to Thermodynamics, Fluid Dynamics, and Mechanical Systems.</li>
  </ul>
</div>

<!-- ═══════════════ EDUCATIONAL TECHNOLOGY ═══════════════ -->
<div class="section-title">Educational Technology</div>
<p class="body-p">
Daily classroom use of <strong>Microsoft Teams</strong> for online instruction and resource 
sharing, <strong>Google Workspace for Education</strong> (Classroom, Drive, Forms) for 
collaborative learning and formative assessment, and the <strong>Microsoft Office Suite</strong> 
for lesson planning, progress tracking, and instructional presentations. Builds 
<strong>interactive simulations, modelling tasks, and digital laboratory activities</strong> 
to support practical Physics, virtual required-practicals, and conceptual modelling &mdash; 
linking EdTech directly to the Pearson Edexcel curriculum.
</p>

<!-- ═══════════════ PROFESSIONAL DEVELOPMENT ═══════════════ -->
<div class="section-title">Professional Development (Current Focus)</div>
<ul class="pd-grid">
  <li>Inclusive pedagogy & differentiation for mixed-attainment classes</li>
  <li>Assessment literacy & AfL (formative and summative)</li>
  <li>Cognitive load theory & scaffolding of difficult Physics topics</li>
  <li>Safeguarding & child protection (PGCEi module)</li>
  <li>Behaviour management & pastoral care in international schools</li>
  <li>Reflective practice & evidence-informed teaching (PGCEi)</li>
</ul>

<!-- ═══════════════ KEY ACHIEVEMENTS ═══════════════ -->
<div class="section-title">Key Achievements & Interests</div>
<ul class="pd-grid">
  <li>Built industrial STEM field-trip programme for Edexcel Physics students.</li>
  <li>Designed KS4/KS5 Physics schemes of work aligned to the Pearson Edexcel specification.</li>
  <li>Produced interactive simulations and digital-lab activities for Physics teaching.</li>
  <li>Led revision and intensive-intervention programmes for terminal-exam cohorts.</li>
  <li>Mentored colleagues on required-practical set-up and laboratory safety.</li>
</ul>

<!-- ═══════════════ REFEREES ═══════════════ -->
<div class="section-title">Referees</div>
<p class="referee-line"><em>References available upon request.</em> Full referee details (three senior referees across teaching and engineering) are supplied on request or attached in the standard referee form.</p>

</body>
</html>
"""

OUTPUT_DIR = "/mnt/d/physics-job-hunter"
HTML_PATH = os.path.join(OUTPUT_DIR, "CV_Mahmoud_Alsini.html")
PDF_PATH  = os.path.join(OUTPUT_DIR, "CV_Mahmoud_Alsini.pdf")

def main():
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)
    print(f"HTML written -> {HTML_PATH}")

    HTML(filename=HTML_PATH).write_pdf(PDF_PATH)
    print(f"PDF  written -> {PDF_PATH}")

    import fitz
    doc = fitz.open(PDF_PATH)
    print(f"PDF pages: {doc.page_count}")
    doc.close()

if __name__ == "__main__":
    main()
