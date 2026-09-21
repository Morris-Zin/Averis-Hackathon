# Review clarity and Malay document-role investigation

The saved live case `a9368a41-9a87-4814-a8fe-40427ac965db` contains `BL_mal.docx` headed `PENDAFTARAN BILL OF LADING` and `SI_mal.docx` headed `ARAHAN PENGHANTARAN`. Both documents have native evidence for all seven fields. The BL role was uncertain; this was not an OCR failure. This case matches the reported symptom, but Congye has not yet confirmed its identity.

Pendaftaran refers to registration, not a draft: [Dewan Bahasa dan Pustaka dictionary](https://prpm.dbp.gov.my/Cari1?d=73980&keyword=pendaftaran). In a six-document live Jev diagnostic with the current unchanged prompt, the original heading remained unknown (0.21 returned role confidence). Changing only the heading to DRAF BIL MUATAN, DRAFT BILL OF LADING or 提单草稿 produced BL at 1.0. BILL OF LADING REGISTRATION APPLICATION remained unknown (0.42); the original Malay SI was SI at 1.0. All six extractions had no field issues. These are single diagnostic calls, not a language-accuracy benchmark. No runtime prompt, threshold, source text or pairing policy was changed.

The UI now calls the probability AI selection confidence, explains that it does not establish source validity or document agreement, and labels source checks requiring review even at 100%. Common field issues explain what was uncertain and what the reviewer should inspect. DeepSeek source-check failures cannot display 'source checks passed'. Unknown future reasons retain a conservative explanation and readable diagnostic code.

Comparison outcomes, source evidence, thresholds and exported results are unchanged. The presentation module owns wording only. Validation and live deployment evidence are saved separately in `.local/teammate-audit/`.
