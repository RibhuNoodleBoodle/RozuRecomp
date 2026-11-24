================================================================================
GEMINI HYDROGEN EXECUTION GUIDE — ROZURECOMP (RULE OF ROSE STATIC RECOMPILATION)
================================================================================

Purpose
-------
This directory contains the step-by-step, self-contained implementation and
verification prompts written by Google Neon (High) for Gemini Hydrogen to build
a genuine native PC static recompilation port of Rule of Rose (PlayStation 2,
NTSC-U, SLUS-21448 v1.00).

How to Run Gemini Hydrogen
--------------------------
1. Always feed ONE step file at a time in order, starting with:
     gemini_hydrogen/Gemini_Step_001.txt
2. Before running a step, check gemini_hydrogen/STEP_INDEX.txt and ./handoff.txt
   to verify prerequisites and confirm whether a CONDITIONAL step (M06–M12) has
   been unblocked by actual runtime evidence from prior steps.
3. Gemini Hydrogen owns all coding, building, debugging, testing, and Git
   commits. Google Neon owns architecture/research revisions and prompt updates.
4. Never skip acceptance tests, never fabricate pass results, and never commit
   proprietary disc media, extracted game binaries, BIOS files, or generated
   game C++ code (Port/generated/).

Mandatory Continuity & Git Rules (Enforced in Every Step)
---------------------------------------------------------
- Read ./handoff.txt completely at the start of every step.
- Work on dedicated feature branch `rozu/port-bringup` (created in Step 001).
- Preserve all pre-existing user files (including Game/Rule of Rose (USA).iso
  and Google_Neon_Rule_of_Rose_Recomp_Architect.txt). Never run destructive
  `git reset --hard` or `git clean -fd`.
- Never use `git add -A` blindly; stage only approved source/doc/test files.
- Commit locally at each verified milestone with step ID in the commit message.
  NEVER push, force-push, rebase, or alter remotes unless explicitly authorized.
- Update ./handoff.txt incrementally (after failures, tests, and commits).

Authoritative Supporting Documents
----------------------------------
- ./handoff.txt                                  (live portable project state)
- architecture/base_repo_audit.md                (sotc-vibe-pc & PS2Recomp audit)
- architecture/reuse_matrix.md                   (A/B/C/D component classification)
- architecture/rule_of_rose_binary_profile.md    (verified SLUS-21448 disc & ELF facts)
- architecture/unknowns_and_risks.md             (R1–R10 risks & unblocking tests)
- architecture/rule_of_rose_port_architecture.md (target modules, pipeline, error handling)
- architecture/build_and_test_strategy.md        (Windows/Linux strategy & Gates G0–G8)
- architecture/milestone_plan.md                 (M00–M12 dependency graph)
- architecture/decisions.md                      (ADR-001 through ADR-010)

Quick Start
-----------
Feed `gemini_hydrogen/Gemini_Step_001.txt` to Gemini Hydrogen first.
