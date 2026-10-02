# Project Goal

> **Status: verbatim Project Goal not yet supplied.**
> The Cloud Project's Goal field was empty at bootstrap (2026-10-02) and no earlier copy exists in the repository.
> When the CTO supplies the text, it replaces the "Pending" section below verbatim, and the interim section is kept
> only where the supplied text does not already cover it. Until then, the interim section is the only authoritative
> product rule set. Do not infer or extend it.

## Pending: verbatim Project Goal

_(to be pasted exactly as supplied by the CTO)_

## Interim authoritative rules (CTO bootstrap message, 2026-10-02)

These are taken from the CTO's own words and carry the CTO's authority.

**Product.** A small, offline seismic shot-matching desktop utility, easy to run and ultimately packaged for normal
end users.

**Responsibilities stay separate.** Detection / matching, QC, and correction are distinct responsibilities and must not
be blurred.

**Matching.** Coordinate evidence is the primary matching mechanism. Sequence / FFID information provides QC evidence
and continuity information, but must not override a strong physical coordinate match merely because recorder and EIVA
sequence values diverged.

Scenario that must remain supported: the recorder stops after FFID 104 and resumes at recorder FFID 105 while EIVA has
advanced to approximately FFID 207. If the coordinates identify the same physical shot, the system must still match
the records correctly, while QC exposes the FFID/sequence divergence.

**QC.** QC reveals anomalies for human inspection.

**Correction.** Correction operates only under the explicitly defined correction rules and must not silently
reinterpret QC anomalies as matching truth.

**Inputs.** Original survey input files are never overwritten.

**Simplicity.** No services, databases, cloud infrastructure, account systems, distributed architecture, unnecessary
abstraction layers, framework migrations, or orchestration complexity inside the product.

## Where the current implementation is described

The technical model as implemented at the baseline (recorder = authoritative reference, EIVA = correction target,
ordered one-to-one alignment, QC separate from correction, correction blockers) is documented in
[docs/recorder-authority-model.md](docs/recorder-authority-model.md) and [PRODUCT.md](PRODUCT.md). Those documents
describe the code; this file defines the product truth. Where they conflict, this file wins and the conflict becomes a
task.
