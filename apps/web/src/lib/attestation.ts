// OCR attestation: any transcription or evidence edit revokes verification.
export function shouldResetVerification(
  previousTranscription: string,
  nextTranscription: string,
  previousEvidence: readonly string[],
  nextEvidence: readonly string[],
): boolean {
  if (previousTranscription !== nextTranscription) return true;
  if (previousEvidence.length !== nextEvidence.length) return true;
  const previous = new Set(previousEvidence);
  for (const id of nextEvidence) {
    if (!previous.has(id)) return true;
  }
  return false;
}
