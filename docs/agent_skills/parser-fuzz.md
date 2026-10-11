name: parser-fuzz
triggers: verhoeff, aadhaar, pan, mrz, parser, regex, ocr noise, driving licence, voter, nagarikta, dates, check digit
- Verhoeff: valid/invalid vectors, O/0 I/1 S/5 B/8 confusions, spaces. PAN `AAAAA9999A` (4th letter = holder type). MRZ weights 7-3-1, TD1/TD2/TD3 lengths.
- Dates: 2-digit years, DD-MM vs MM-DD, leap days, impossible dates, issue before expiry, DOB vs age.
- Build layout variants (field order, columns, label spellings, bilingual, boilerplate, signature beside name, several dates) x OCR noise x3 levels. Report field accuracy with n.
- A loosened rule needs a measured false-accept rate on random strings. Cross-field failures route to REVIEW.
- Fixtures: fake values only (`TEST USER`), numbers that fail real issuance rules, never values from a real card.
