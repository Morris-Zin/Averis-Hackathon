// Pure guards for case identity; the review hook consumes these rules.
export function isRequestedCaseLoaded(
  requestedId: string,
  loadedId: string | null,
): boolean {
  return Boolean(requestedId) && loadedId === requestedId;
}

export function shouldIgnoreLateResponse(
  requestedId: string,
  responseId: string,
  responseSequence: number,
  currentSequence: number,
): boolean {
  return (
    responseSequence !== currentSequence ||
    !requestedId ||
    responseId !== requestedId
  );
}

export function shouldInvalidateOnNavigate(
  previousRequestedId: string,
  nextRequestedId: string,
): boolean {
  return previousRequestedId !== nextRequestedId;
}
