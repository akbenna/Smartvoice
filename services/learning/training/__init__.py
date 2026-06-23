"""
Trainingsdata-export (Fase 3).

Exporteert uit de feedbackloop de datasets voor zwaardere modelverbetering:
- ASR-postcorrectie (SFT): transcript_original -> transcript_corrected (geen audio)
- SOEP-voorkeuren (DPO): soep_original (rejected) vs soep_corrected (chosen)

Pure builders + DB-export (raw SQL). De trainingsscripts staan los en draaien
op een GPU-machine met de juiste dependencies.
"""
