# Local Xcode Build Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan.

**Goal:** Make local macOS compilation the default and stop automatic GitHub builds.
**Architecture:** A checked local entry invokes the existing shared module compiler,
then optionally the existing external-display IPA packer. Every run has fresh output.
**Tech Stack:** Bash 3.2, Python 3.11+, Xcode/iPhoneOS SDK.
**Spec:** docs/superpowers/specs/2026-11-02-local-build-design.md

## Global Constraints

- No private game files in GitHub or source delivery.
- No signing or installation; compilation is not hardware verification.
- No Xcode execution is possible in the connected Linux environment.

## Review Focus

- Paths with spaces and invocation outside the repository must work.
- Missing prerequisites must not create misleading build output.
- Failed compilation must not package a stale module.
- Optional IPA assembly must preserve existing controls and reject existing output.
- Source ZIP extraction without git must retain source identification.

### Task 1: Local build and default workflow

- [x] Write/run failing CLI tests for platform check, check-only behavior, path handling and failed compiler propagation.
- [x] Extract shared compiler; implement local script and Build-Local.command.
- [x] Run CLI and existing portable tests plus shell validation.
- [x] Make CI manual only and update Chinese/English local build instructions.
- [ ] Review changes, commit selected source updates, publish without starting CI.
- [ ] Deliver a source ZIP with truthful verification status.

## Verification and review

Python: 26 total, 25 passed, 1 original-private-IPA test skipped. External
geometry: 20 cases; touch motion: 15 cases. Shell syntax and manual-only YAML
checks passed. Fresh read-only review approved with no findings.

Actual Xcode compilation, macOS Bash/Finder execution, real IPA assembly, HDMI,
gameplay and frame pacing remain unverified because the connected environment is
Linux and the private original IPA is unavailable. No signing/installability claim.
