# Data Confidence Audit

Generated: July 15, 2026

This dashboard now treats data confidence as separate from sourcing score. A profile can look interesting commercially but still be blocked from business review if the evidence only shows a named breeder, not a legal owner or verified company relationship.

## Current Audit Counts

- Profiles audited: 14,138
- High-confidence profiles: 8
- Medium-confidence profiles: 20
- Low-confidence profiles: 61
- Unverified profiles: 14,049
- Profiles ready for business review: 9
- Holder verification required: 482
- Legal entity profile needed: 333
- Legal owner needs company profile: 48

## What Changed

- Added `data/data_confidence.json` and `data/data_confidence.csv` as the main confidence layer.
- Added `data/rollup_review_queue.csv` for the highest-priority owner and breeder rollup review queue.
- Kept data confidence as an internal rebuild/audit layer rather than a visible dashboard tab.
- Added source-backed profile seeds for Edward Vinson Limited, Angus Soft Fruits, Stargrow Cultivar Development, and ABZ Seeds.
- Updated the profile audit to distinguish confirmed legal-owner records from breeder-only CPVO signals.

## Highest-Priority Cleanup Buckets

- Holder verification: high-count CPVO breeder-only profiles should not be treated as acquisition targets until applicant or holder evidence is verified.
- Legal entity profile creation: company-like names with records need sourced websites, contact paths, LinkedIn checks, and cultivar evidence.
- Company enrichment: existing company profiles need stronger contact, LinkedIn, news, and cultivar-count evidence before being considered diligence-ready.
- Public program filtering: universities, national programs, and research institutes should remain context records unless there is a commercialization vehicle worth tracking.

## Independent Rollup QA Checkpoint

The top rollup-risk profiles are all currently `holder_verification_required`. None should be treated as acquisition targets until the legal holder or applicant is verified.

| Priority | Profile | Records | Candidate Parent | Current Read |
| --- | --- | ---: | --- | --- |
| 1 | Arsene et Laurence Maillard | 1,013 | Agro Selections Fruits S.A.S. | Partial US evidence only; CPVO bulk is breeder-only. |
| 2 | Rene Monteux-Caillet | 513 | None | No reliable company holder in local data. |
| 3 | Laurence Maillard | 459 | Agro Selections Fruits S.A.S. | Partial evidence and double-count risk with combined Maillard profile. |
| 4 | Vincent David Andrew Mazzardis | 260 | None | No local parent evidence. |
| 5 | Sat 9413 Frutaria | 214 | None | CPVO/ES breeder-only cluster. |
| 6 | Fred W. Anderson | 188 | None | No company relationship evidenced locally. |
| 7 | Sedov Evgenij NIKOLAEVICh | 179 | None | RU breeder-only signal. |
| 8 | IVIA | 151 | None | Entity-like, but still only breeder/inventor signal locally. |
| 9 | Pepinieres et Roseraies Georges Delbard | 144 | None | Company-like name, but no legal-owner records locally. |
| 10 | FRESAS NUEVOS MATERIALES, S.A. | 144 | None | Entity-like but breeder-only in local confidence data. |
| 11 | Masia Ciscar S.A. | 143 | None | Entity-like but no legal-owner support locally. |
| 12 | James F. Hancock | 138 | Berry Blue | Partial only; split Berry Blue-assigned patents from public/university records before rolling up. |
| 13 | TROShIN Leonid PETROVICh | 128 | None | RU grape breeder-only cluster. |
| 14 | Gianfranco Castagnoli | 127 | None | CIV-looking variety names are not holder evidence. |
| 15 | Ca Merced | 127 | None | Weak local evidence; raw source cleanup needed before rollup analysis. |

## Practical Rule

Use the `Sourcing` tab to find interesting targets. Treat the confidence files and rollup review queue as internal QA outputs that should be checked before trusting a profile for business review.
