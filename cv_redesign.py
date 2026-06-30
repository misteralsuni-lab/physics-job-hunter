#!/usr/bin/env python3
"""
Generate a redesigned, ATS-optimised CV for Mahmoud Alsini
Target: Secondary Physics Teacher (Pearson Edexcel IGCSE & A-Level)
        at British international schools in UAE, Qatar, Saudi Arabia, GCC
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
    margin: 1.2cm 1.5cm 1.2cm 1.5cm;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: 'Segoe UI', 'Calibri', 'Helvetica Neue', Arial, sans-serif;
    font-size: 9pt;
    line-height: 1.42;
    color: #1a1a1a;
    background: #fff;
  }

  /* ── HEADER ── */
  .header {
    text-align: center;
    padding-bottom: 5px;
    border-bottom: 2px solid #1a3a5c;
    margin-bottom: 8px;
  }
  .header h1 {
    font-size: 18pt;
    font-weight: 700;
    color: #1a3a5c;
    letter-spacing: 0.5pt;
    margin-bottom: 1px;
  }
  .header .subtitle {
    font-size: 9pt;
    color: #444;
    font-weight: 500;
    margin-bottom: 3px;
  }
  .header .contact {
    font-size: 8pt;
    color: #555;
  }
  .header .contact span {
    display: inline-block;
    margin: 0 4px;
  }
  .header .contact .sep {
    color: #bbb;
  }

  /* ── SECTION HEADINGS ── */
  .section-title {
    font-size: 9.5pt;
    font-weight: 700;
    color: #1a3a5c;
    text-transform: uppercase;
    letter-spacing: 0.8pt;
    border-bottom: 0.8px solid #ccc;
    padding-bottom: 1px;
    margin-top: 8px;
    margin-bottom: 4px;
  }
  .section-title:first-of-type {
    margin-top: 0;
  }

  /* ── PROFILE ── */
  .profile-text {
    font-size: 8.5pt;
    line-height: 1.42;
    text-align: justify;
    margin-bottom: 1px;
  }

  /* ── COMPETENCIES GRID ── */
  .competencies {
    display: flex;
    flex-wrap: wrap;
    gap: 2px 0;
    margin-bottom: 4px;
  }
  .competency-col {
    flex: 0 0 33.33%;
    padding-right: 8px;
  }
  .competency-col ul {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .competency-col ul li {
    font-size: 8pt;
    padding: 0 0 0 10px;
  }
  .competency-col ul li::before {
    content: "\\25CF";
    position: absolute;
    left: 0;
    color: #1a3a5c;
    font-size: 5pt;
    top: 1px;
  }

  /* ── Education ── */
  .edu-entry {
    margin-bottom: 5px;
  }
  .edu-entry .edu-title {
    font-weight: 600;
    font-size: 9pt;
  }
  .edu-entry .edu-meta {
    font-size: 8.5pt;
    color: #555;
  }
  .edu-entry .edu-note {
    font-size: 8.5pt;
    color: #666;
    font-style: italic;
  }

  /* ── JOB ENTRIES ── */
  .job {
    margin-bottom: 5px;
    page-break-inside: avoid;
  }
  .job-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  .job-title {
    font-weight: 700;
    font-size: 9pt;
    color: #1a3a5c;
  }
  .job-org {
    font-weight: 600;
    font-size: 8.5pt;
  }
  .job-dates {
    font-size: 8pt;
    color: #666;
    white-space: nowrap;
  }
  .job-location {
    font-size: 8pt;
    color: #777;
    margin-bottom: 1px;
  }
  .job ul {
    list-style: none;
    padding: 0;
    margin: 1px 0 0 0;
  }
  .job ul li {
    font-size: 8.5pt;
    line-height: 1.38;
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

  /* ── ENGAGEMENT NOTE ── */
  .concurrent-note {
    font-size: 8pt;
    color: #666;
    font-style: italic;
    margin-top: -3px;
    margin-bottom: 4px;
  }

  /* ── REFEREES ── */
  .referee-line {
    font-size: 8.5pt;
    line-height: 1.5;
  }

  /* ── PAGE BREAK ── */
  .page-break {
    page-break-before: always;
  }

  /* ── MISC ── */
  .small-meta { font-size: 8pt; color: #777; }
  .no-break { page-break-inside: avoid; }
</style>
</head>
<body>

<!-- ═══════════════ HEADER ═══════════════ -->
<div class="header">
  <h1>MAHMOUD ALSINI</h1>
  <div class="subtitle">Secondary Physics Teacher &bull; Pearson Edexcel IGCSE &amp; A-Level &bull; Mechanical Engineer</div>
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
Dedicated Physics educator and qualified Mechanical Engineer with a B.Sc. in Engineering Science, 
currently completing a PGCEi (Postgraduate Certificate in Education – International) with Liverpool John 
Moores University (LJMU), UK. I bring an <strong>"Applied Mastery"</strong> approach to the international 
secondary classroom—bridging theoretical physics with real-world industrial engineering to engage 
high-achieving students preparing for elite university pathways in Engineering, Architecture, and the 
Physical Sciences. Experienced delivering <strong>Pearson Edexcel IGCSE and A-Level Physics</strong> at 
registered British curriculum examination centres in Tripoli. I foster <strong>inquiry-based, 
student-centred learning environments</strong> where students think like engineers—understanding the 
physical and mechanical logic behind formulae rather than memorising them. Committed to 
<strong>assessment for learning</strong>, <strong>differentiation</strong>, and <strong>inclusive 
pedagogy</strong>, and actively developing UK-standard teaching expertise through PGCEi training. 
My engineering background provides unique credibility in teaching Practical Physics, STEM integration, 
and laboratory-based learning.
</p>

<!-- ═══════════════ CORE COMPETENCIES ═══════════════ -->
<div class="section-title">Core Competencies</div>
<div class="competencies">
  <div class="competency-col">
    <ul>
      <li>Pearson Edexcel IGCSE Physics</li>
      <li>Pearson Edexcel A-Level Physics</li>
      <li>Curriculum Planning &amp; Mapping</li>
      <li>Assessment for Learning (AfL)</li>
      <li>Differentiation &amp; Scaffolding</li>
    </ul>
  </div>
  <div class="competency-col">
    <ul>
      <li>Inclusive Education &amp; SEN Awareness</li>
      <li>Behaviour Management</li>
      <li>Laboratory Safety &amp; Practical Physics</li>
      <li>STEM Education &amp; Cross-Curricular Links</li>
      <li>Inquiry-Based Learning (IBL)</li>
    </ul>
  </div>
  <div class="competency-col">
    <ul>
      <li>Educational Technology Integration</li>
      <li>Microsoft Teams &amp; Office Suite</li>
      <li>Google Workspace for Education</li>
      <li>Formative &amp; Summative Assessment</li>
      <li>Examination Standardisation</li>
    </ul>
  </div>
</div>

<!-- ═══════════════ EDUCATION & QUALIFICATIONS ═══════════════ -->
<div class="section-title">Education &amp; Qualifications</div>

<div class="edu-entry no-break">
  <div class="edu-title">PGCEi (Postgraduate Certificate in Education – International) <span class="edu-meta">— In Progress</span></div>
  <div class="edu-meta">Liverpool John Moores University (LJMU), UK &bull; Module 7532-PCEI</div>
  <div class="edu-note">UK-standard pedagogical training covering inclusive education, assessment theory, curriculum design, and reflective practice.</div>
</div>

<div class="edu-entry no-break">
  <div class="edu-title">B.Sc. Mechanical Engineering (Engineering Science)</div>
  <div class="edu-meta">University of Tripoli, Faculty of Engineering, Libya &bull; Graduated 2020</div>
  <div class="edu-note">Key modules: Mechanics, Thermodynamics, Fluid Dynamics, Electricity &amp; Magnetism — forming the theoretical foundation for Physics instruction.</div>
</div>

<!-- ═══════════════ PROFESSIONAL TEACHING EXPERIENCE ═══════════════ -->
<div class="section-title">Teaching Experience</div>

<!-- Job 1 -->
<div class="job no-break">
  <div class="job-header">
    <div>
      <span class="job-title">Physics Teacher</span>
      <span class="job-org"> — Vision International School</span>
      <span class="job-location">(Registered Pearson Edexcel Centre), Tripoli, Libya</span>
    </div>
    <div class="job-dates">Sept 2023 – Present</div>
  </div>
  <ul>
    <li>Direct the Physics provision across Key Stages 4 and 5, managing curriculum delivery, assessment design, and academic standardisation for IGCSE and A-Level cohorts at a registered Pearson Edexcel international examination centre.</li>
    <li>Design and deliver rigorous, specification-aligned schemes of work covering Mechanics, Waves, Electricity &amp; Magnetism, Thermal Physics, Particle Physics, and Practical Skills for both IGCSE and A-Level pathways.</li>
    <li>Pioneer industry-linked STEM field trips connecting abstract classroom theory to real-world industrial applications—enhancing student engagement with Practical STEM learning and career awareness in engineering.</li>
    <li>Cultivate a culture of "Applied Mastery" by embedding engineering case studies and mechanical problem-solving into Physics lessons, providing students with analytical frameworks essential for university study in STEM disciplines.</li>
    <li>Implement formative Assessment for Learning strategies—including hinge questions, exit tickets, and targeted feedback—to monitor progress and adapt instruction to diverse learner needs.</li>
  </ul>
</div>

<!-- Job 2 -->
<div class="job no-break">
  <div class="job-header">
    <div>
      <span class="job-title">Physics Teacher (IGCSE &amp; A-Level)</span>
      <span class="job-org"> — Kids Academy School</span>
      <span class="job-location">(Cognia Accredited), Tripoli, Libya</span>
    </div>
    <div class="job-dates">2024</div>
  </div>
  <div class="concurrent-note">Concurrent appointment alongside Vision International School</div>
  <ul>
    <li>Managed a dual teaching portfolio, delivering targeted small-group Physics instruction and intensive revision sessions to prepare IGCSE and A-Level candidates for terminal examinations.</li>
    <li>Diagnosed individual student learning gaps in complex concepts—such as electromagnetic induction and circular motion—and designed bespoke intervention plans to elevate examination readiness.</li>
    <li>Integrated practical laboratory work with theoretical instruction to strengthen students' understanding of experimental methods and data analysis skills required by the Pearson Edexcel specification.</li>
  </ul>
</div>

<!-- Job 3 -->
<div class="job no-break">
  <div class="job-header">
    <div>
      <span class="job-title">Chemistry Teacher</span>
      <span class="job-org"> — Ladybird International School</span>
      <span class="job-location">Tripoli, Libya</span>
    </div>
    <div class="job-dates">2022 – 2023</div>
  </div>
  <ul>
    <li>Prepared diverse cohorts of secondary students for international Science examinations through rigorous progress monitoring, data-driven target-setting, and tailored pedagogical strategies.</li>
    <li>Established strong foundational understanding of scientific principles—including atomic structure, chemical bonding, and reaction kinetics—enabling smooth transition of students into upper-secondary Science curricula.</li>
    <li>Applied inclusive teaching practices to support learners with varying prior attainment levels, ensuring all students could access and engage with challenging scientific content.</li>
  </ul>
</div>

<!-- ═══════════════ ENGINEERING EXPERIENCE ═══════════════ -->
<div class="section-title">Engineering &amp; Technical Experience</div>

<div class="job no-break">
  <div class="job-header">
    <div>
      <span class="job-title">Technical Training and Diagnostics Specialist</span>
      <span class="job-org"> — Alsahl Group</span>
      <span class="job-location">Tripoli, Libya</span>
    </div>
    <div class="job-dates">2021 – 2022</div>
  </div>
  <ul>
    <li>Served as the technical authority and primary educator for professional engineering teams, designing and delivering comprehensive training programmes on the integration, diagnostics, and maintenance of new heavy machinery (generators and forklifts).</li>
    <li>Conducted advanced technical research to develop efficient diagnostic workflows, directly enhancing operational capacity and machinery lifecycle management across the organisation.</li>
    <li>Translated complex mechanical system principles into accessible, practical instruction for technicians—a skill directly transferable to scaffolding Physics concepts for diverse learners.</li>
  </ul>
</div>

<div class="job no-break">
  <div class="job-header">
    <div>
      <span class="job-title">Engineering Intern</span>
      <span class="job-org"> — Accuracy for Maintenance</span>
      <span class="job-location">Tripoli, Libya</span>
    </div>
    <div class="job-dates">2020 – 2021</div>
  </div>
  <ul>
    <li>Assisted in troubleshooting, diagnostic analysis, and routine maintenance of industrial mechanical systems, gaining hands-on exposure to Thermodynamics, Fluid Dynamics, and Mechanical Systems in operational settings.</li>
    <li>Developed practical problem-solving and analytical reporting skills that underpin an authentic, application-driven approach to Physics teaching.</li>
  </ul>
</div>

<!-- ═══════════════ EDUCATIONAL TECHNOLOGY ═══════════════ -->
<div class="section-title">Educational Technology</div>
<p style="font-size:8.8pt; line-height:1.5; margin-bottom:4px;">
Proficient in leveraging digital tools to enhance teaching, assessment, and classroom communication. 
Experienced with <strong>Microsoft Teams</strong> for online instruction, resource sharing, and 
assignment management; <strong>Google Workspace for Education</strong> (Classroom, Drive, Docs, 
Forms) for collaborative learning and formative assessment; and the full <strong>Microsoft Office 
Suite</strong> (Word, Excel, PowerPoint) for lesson planning, data analysis, and instructional 
presentation. Integrate simulation software and digital lab platforms to support virtual practical 
work and conceptual modelling in Physics.
</p>

<!-- ═══════════════ PROFESSIONAL DEVELOPMENT ═══════════════ -->
<div class="section-title">Professional Development</div>
<p style="font-size:8.8pt; line-height:1.5; margin-bottom:4px;">
<strong>PGCEi Candidate</strong>, Liverpool John Moores University (2025–2026) — actively developing 
research-informed practice in inclusive pedagogy, curriculum design, assessment theory, and reflective 
teaching. Module 7532-PCEI focuses on international education contexts and evidence-based strategies 
for student engagement and progress.
</p>

<!-- ═══════════════ REFEREES ═══════════════ -->
<div class="section-title">Referees</div>
<div class="referee-line">
<strong>Sufana Mahmoud Ben Mansur</strong> — Academic Director, Vision International School<br>
<em>Relationship:</em> Head of Secondary and Direct Academic Supervisor<br>
Email: Sufana@vis.sch.ly &nbsp;|&nbsp; Phone: +218 92-8585265
</div>
<div style="height:4px;"></div>
<div class="referee-line">
<strong>Muhanad Al-Barrah</strong> — VP of Maintenance Division, Al-Sahal Group<br>
<em>Relationship:</em> Former Direct Technical Supervisor<br>
Email: Muhanad.albarrah@alsahlgroup.com &nbsp;|&nbsp; Phone: +218 91-2612150
</div>
<div style="height:4px;"></div>
<div class="referee-line">
<strong>Eng. Abdulraouf Mohammed Al-Naas</strong> — Assistant Professor &amp; Director of Programme Office, University of Tripoli<br>
<em>Relationship:</em> Former Research Supervisor and Professor<br>
Email: a.naas@uot.edu.ly &nbsp;|&nbsp; Phone: +218 91-5021502
</div>

</body>
</html>
"""

OUTPUT_DIR = "/mnt/d/physics-job-hunter"
HTML_PATH = os.path.join(OUTPUT_DIR, "CV_Mahmoud_Alsini.html")
PDF_PATH = os.path.join(OUTPUT_DIR, "CV_Mahmoud_Alsini.pdf")

def main():
    # Write HTML
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)
    print(f"HTML written to {HTML_PATH}")

    # Convert to PDF
    HTML(filename=HTML_PATH).write_pdf(PDF_PATH)
    print(f"PDF written to {PDF_PATH}")

    # Check page count (weasyprint embeds page count info)
    import fitz  # pymupdf
    doc = fitz.open(PDF_PATH)
    print(f"PDF pages: {doc.page_count}")
    doc.close()

if __name__ == "__main__":
    main()
